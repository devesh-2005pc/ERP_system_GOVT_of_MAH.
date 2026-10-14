"""
License token signing & verification.

ARCHITECTURE:
  - `sign_license()` uses an RSA PRIVATE key and is only ever run by
    Anthropic^H^H^H by the vendor/publisher on a separate offline machine
    (see scripts/issue_license.py). It is NEVER imported by the shipped
    application.
  - `verify_license()` uses only the RSA PUBLIC key, which IS shipped inside
    the application. It can confirm a token was signed by the real private
    key and hasn't been tampered with, but it cannot forge new tokens.

This gives genuine cryptographic device-binding: an attacker holding only
the shipped .exe (and therefore only the public key) cannot mint a new
valid license for an unauthorized device or extend an expired one.
"""
import json
import base64
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


@dataclass
class LicenseInfo:
    valid: bool
    reason: str
    payload: dict | None = None


def generate_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    return private_key, private_key.public_key()


def save_private_key(private_key, path: str, password: bytes | None = None):
    encryption = serialization.BestAvailableEncryption(password) if password else serialization.NoEncryption()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    with open(path, "wb") as f:
        f.write(pem)


def save_public_key(public_key, path: str):
    pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(path, "wb") as f:
        f.write(pem)


def load_private_key(path: str, password: bytes | None = None):
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=password)


def load_public_key(path: str):
    with open(path, "rb") as f:
        return serialization.load_pem_public_key(f.read())


def sign_license(private_key, payload: dict) -> dict:
    """payload should include: license_key, device_fingerprint, issued_at,
    expires_at (ISO strings), max_devices, office_name."""
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = private_key.sign(
        body,
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
        hashes.SHA256(),
    )
    return {"payload": payload, "signature": base64.b64encode(signature).decode()}


def verify_license(public_key, token: dict, current_fingerprint: str | None = None) -> LicenseInfo:
    try:
        payload = token["payload"]
        signature = base64.b64decode(token["signature"])
    except (KeyError, TypeError, ValueError):
        return LicenseInfo(False, "Malformed license token")

    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    try:
        public_key.verify(
            signature, body,
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
            hashes.SHA256(),
        )
    except Exception:
        return LicenseInfo(False, "Signature verification failed - token is invalid or tampered")

    expires_at = datetime.fromisoformat(payload["expires_at"])
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) > expires_at:
        return LicenseInfo(False, "License has expired", payload)

    if current_fingerprint and payload.get("device_fingerprint") != current_fingerprint:
        return LicenseInfo(False, "License is not valid for this device", payload)

    return LicenseInfo(True, "OK", payload)
