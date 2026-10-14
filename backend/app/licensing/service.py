import json
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.licensing.tokens import load_public_key, verify_license, LicenseInfo
from app.licensing.fingerprint import compute_fingerprint, get_computer_name
from app.models.system import Device

settings = get_settings()


def get_current_license_status() -> LicenseInfo:
    pub_path = settings.LICENSE_PUBLIC_KEY_PATH
    token_path = settings.LICENSE_TOKEN_PATH
    if not os.path.exists(pub_path):
        return LicenseInfo(False, "Public key not installed - application not properly packaged")
    if not os.path.exists(token_path):
        return LicenseInfo(False, "No license token installed - activation required")

    public_key = load_public_key(pub_path)
    token = json.loads(Path(token_path).read_text())
    fingerprint = compute_fingerprint()
    return verify_license(public_key, token, current_fingerprint=None)  # fingerprint check per-device done separately


def activate_device(db: Session, department_id, computer_name: str | None = None) -> Device:
    """Registers THIS machine as an active device under the office license,
    enforcing the max_devices cap embedded in the signed license."""
    status = get_current_license_status()
    if not status.valid:
        raise ValueError(f"Cannot activate device: {status.reason}")

    fingerprint = compute_fingerprint()
    existing = db.query(Device).filter(Device.device_fingerprint == fingerprint).first()
    if existing:
        if existing.status == "REVOKED":
            raise ValueError("This device's license has been revoked by the Manager")
        return existing

    active_count = db.query(Device).filter(Device.status == "ACTIVE").count()
    max_devices = status.payload.get("max_devices", 1)
    if active_count >= max_devices:
        raise ValueError(f"Maximum licensed devices ({max_devices}) already activated")

    device = Device(
        device_fingerprint=fingerprint,
        computer_name=computer_name or get_computer_name(),
        department_id=department_id,
        status="ACTIVE",
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device
