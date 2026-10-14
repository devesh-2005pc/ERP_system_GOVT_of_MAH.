import hashlib
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHash
from jose import jwt, JWTError

from app.core.config import get_settings

settings = get_settings()

# Argon2id, tuned params (time_cost/memory_cost can be raised on beefier
# office servers; these are safe reasonable defaults for a desktop-class
# office server).
_ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)


def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, plain)
    except (VerifyMismatchError, InvalidHash):
        return False


def needs_rehash(hashed: str) -> bool:
    return _ph.check_needs_rehash(hashed)


def create_access_token(subject: str, extra_claims: dict) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": subject,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        **extra_claims,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def new_refresh_token() -> tuple[str, str]:
    """Returns (raw_token_to_give_client, hash_to_store_in_db)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
