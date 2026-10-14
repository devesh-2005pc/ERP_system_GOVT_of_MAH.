"""
Authentication + authorization dependencies.

CRITICAL DESIGN RULE (explicit requirement from the client):
Departments cannot see each other's operational data. Only MANAGER and
SUB_ADMIN can see and edit every department's data. This is enforced HERE,
at the dependency/service layer that every router must go through — never
only hidden in the frontend. A Store user calling a Dispatch endpoint (even
if they somehow know the URL) gets a 403, not filtered/empty data — 403 by
default per unauthorized-collection access, per section 26 (no IDOR).
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_token
from app.core.database import get_db
from app.models.user import User
from app.models.enums import DepartmentCode, CROSS_DEPARTMENT_ROLES

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(token: str | None = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise credentials_exception
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        raise credentials_exception
    return user


def get_current_department_code(user: User) -> DepartmentCode:
    return user.department.code


def is_cross_department(user: User) -> bool:
    """True for MANAGER and SUB_ADMIN — the only roles allowed to see/edit
    every department's data."""
    return get_current_department_code(user) in CROSS_DEPARTMENT_ROLES


def is_manager(user: User) -> bool:
    return get_current_department_code(user) == DepartmentCode.MANAGER


def require_departments(*allowed: DepartmentCode):
    """Dependency factory: allow only the given departments, PLUS
    MANAGER/SUB_ADMIN always (per the cross-department access rule)."""
    allowed_set = set(allowed) | CROSS_DEPARTMENT_ROLES

    def _dep(user: User = Depends(get_current_user)) -> User:
        if get_current_department_code(user) not in allowed_set:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this department's data")
        return user

    return _dep


def require_manager(user: User = Depends(get_current_user)) -> User:
    if not is_manager(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager-only action")
    return user


def require_manager_or_subadmin(user: User = Depends(get_current_user)) -> User:
    if not is_cross_department(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Manager/Sub-Admin only action")
    return user


def scoped_department_filter(user: User, requested_department_id=None):
    """For endpoints where a caller *within* an allowed set of departments
    should still only see their OWN department's rows, unless they are
    MANAGER/SUB_ADMIN (who may optionally filter by any department_id).
    Returns the department_id to filter by, or None to mean 'no filter'
    (only ever returned for cross-department roles)."""
    if is_cross_department(user):
        return requested_department_id  # may be None = all departments
    return user.department_id
