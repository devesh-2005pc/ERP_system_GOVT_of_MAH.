import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_manager_or_subadmin, require_manager
from app.licensing.service import get_current_license_status, activate_device
from app.licensing.fingerprint import compute_fingerprint
from app.models.system import Device
from app.models.user import User
from app.services import audit as audit_service

router = APIRouter(prefix="/api/license", tags=["licensing"])


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    device_fingerprint: str
    computer_name: Optional[str] = None
    status: str


@router.get("/status")
def license_status(user: User = Depends(require_manager_or_subadmin)):
    status = get_current_license_status()
    result = {"valid": status.valid, "reason": status.reason, "this_device_fingerprint": compute_fingerprint()}
    if status.payload:
        result.update({
            "office_name": status.payload.get("office_name"),
            "expires_at": status.payload.get("expires_at"),
            "max_devices": status.payload.get("max_devices"),
        })
    return result


@router.post("/activate-this-device")
def activate_this_device(user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    try:
        device = activate_device(db, department_id=user.department_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    audit_service.record(db, user=user, action="DEVICE_ACTIVATED", entity_type="Device", entity_id=device.id)
    db.commit()
    return {"ok": True, "device_id": str(device.id), "fingerprint": device.device_fingerprint}


@router.get("/devices", response_model=list[DeviceOut])
def list_devices(user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    return db.query(Device).all()


@router.post("/devices/{device_id}/revoke")
def revoke_device(device_id: uuid.UUID, user: User = Depends(require_manager), db: Session = Depends(get_db)):
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.status = "REVOKED"
    audit_service.record(db, user=user, action="DEVICE_REVOKED", entity_type="Device", entity_id=device.id)
    db.commit()
    return {"ok": True}
