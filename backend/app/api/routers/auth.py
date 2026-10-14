from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.auth.security import (
    verify_password, hash_password, create_access_token,
    new_refresh_token, hash_refresh_token, decode_token,
)
from app.auth.deps import get_current_user
from app.models.user import User, RefreshSession, LoginHistory
from app.schemas.auth import LoginRequest, TokenResponse, RefreshRequest, ChangePasswordRequest, MeResponse
from app.services import audit as audit_service

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    user = db.query(User).filter(User.employee_id == payload.employee_id).first()

    def fail(reason: str):
        db.add(LoginHistory(
            user_id=user.id if user else None,
            employee_id_attempted=payload.employee_id,
            success=False, reason=reason, ip_address=ip,
            user_agent=request.headers.get("user-agent"),
        ))
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid employee ID or password")

    if not user or not user.is_active:
        fail("unknown_or_inactive_user")

    if user.locked_until and user.locked_until > datetime.utcnow():
        fail("account_locked")

    if not verify_password(payload.password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        fail("bad_password")

    # success
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"employee_id": user.employee_id, "dept": user.department.code.value},
    )
    raw_refresh, hashed_refresh = new_refresh_token()
    session = RefreshSession(
        user_id=user.id,
        token_hash=hashed_refresh,
        expires_at=datetime.utcnow() + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES),
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
    )
    db.add(session)
    db.add(LoginHistory(user_id=user.id, employee_id_attempted=user.employee_id, success=True, ip_address=ip,
                         user_agent=request.headers.get("user-agent")))
    audit_service.record(db, user=user, action="LOGIN", entity_type="User", entity_id=user.id, ip_address=ip)
    db.commit()

    return TokenResponse(
        access_token=access_token,
        refresh_token=raw_refresh,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.query(RefreshSession).filter(RefreshSession.token_hash == token_hash).first()
    if not session or not session.is_valid():
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    idle_cutoff = datetime.utcnow() - timedelta(minutes=settings.SESSION_IDLE_TIMEOUT_MINUTES)
    if session.last_seen_at < idle_cutoff:
        session.revoked_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired due to inactivity")

    user = db.query(User).filter(User.id == session.user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(status_code=401, detail="User no longer active")

    session.last_seen_at = datetime.utcnow()
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"employee_id": user.employee_id, "dept": user.department.code.value},
    )
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=payload.refresh_token,
                          must_change_password=user.must_change_password)


@router.post("/logout")
def logout(payload: RefreshRequest, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(payload.refresh_token)
    session = db.query(RefreshSession).filter(RefreshSession.token_hash == token_hash).first()
    if session:
        session.revoked_at = datetime.utcnow()
        db.commit()
    return {"ok": True}


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    return MeResponse(
        id=user.id, employee_id=user.employee_id, full_name=user.full_name,
        department_code=user.department.code.value, department_name=user.department.name,
        is_department_admin=user.is_department_admin,
    )


@router.post("/change-password")
def change_password(payload: ChangePasswordRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    audit_service.record(db, user=user, action="PASSWORD_CHANGED", entity_type="User", entity_id=user.id)
    db.commit()
    return {"ok": True}
