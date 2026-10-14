import json
from datetime import datetime, timedelta, timezone

from app.licensing.tokens import generate_keypair, sign_license, verify_license


def _make_token(private_key, **overrides):
    payload = {
        "license_key": "MUDRA-TEST-0001",
        "office_name": "Test Press",
        "device_fingerprint": "abc123",
        "max_devices": 3,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=365)).isoformat(),
    }
    payload.update(overrides)
    return sign_license(private_key, payload)


def test_valid_license_verifies():
    private_key, public_key = generate_keypair()
    token = _make_token(private_key)
    result = verify_license(public_key, token, current_fingerprint="abc123")
    assert result.valid


def test_tampered_payload_is_rejected():
    private_key, public_key = generate_keypair()
    token = _make_token(private_key)
    # Attacker tries to extend the expiry without re-signing
    token["payload"]["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=99999)).isoformat()
    result = verify_license(public_key, token, current_fingerprint="abc123")
    assert not result.valid
    assert "Signature" in result.reason


def test_token_signed_by_different_key_is_rejected():
    private_key_a, _ = generate_keypair()
    _, public_key_b = generate_keypair()
    token = _make_token(private_key_a)
    result = verify_license(public_key_b, token, current_fingerprint="abc123")
    assert not result.valid


def test_expired_license_is_rejected():
    private_key, public_key = generate_keypair()
    token = _make_token(
        private_key,
        issued_at=(datetime.now(timezone.utc) - timedelta(days=400)).isoformat(),
        expires_at=(datetime.now(timezone.utc) - timedelta(days=35)).isoformat(),
    )
    result = verify_license(public_key, token, current_fingerprint="abc123")
    assert not result.valid
    assert "expired" in result.reason.lower()


def test_wrong_device_fingerprint_is_rejected():
    private_key, public_key = generate_keypair()
    token = _make_token(private_key, device_fingerprint="THE-REAL-DEVICE")
    result = verify_license(public_key, token, current_fingerprint="SOME-OTHER-DEVICE")
    assert not result.valid
    assert "device" in result.reason.lower()
