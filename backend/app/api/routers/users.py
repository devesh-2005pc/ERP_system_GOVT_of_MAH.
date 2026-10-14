import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_manager_or_subadmin, require_manager
from app.auth.security import hash_password
from app.models.enums import DepartmentCode
from app.models.user import User, Department
from app.services import audit as audit_service

router = APIRouter(prefix="/api/users", tags=["users"])


class UserCreate(BaseModel):
    employee_id: str
    full_name: str
    email: Optional[str] = None
    password: str
    department_code: DepartmentCode
    is_department_admin: bool = False


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    employee_id: str
    full_name: str
    email: Optional[str] = None
    department_id: uuid.UUID
    is_active: bool
    is_department_admin: bool


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    department_code: Optional[DepartmentCode] = None
    is_active: Optional[bool] = None
    is_department_admin: Optional[bool] = None


@router.get("", response_model=list[UserOut])
def list_users(user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    return db.query(User).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    if db.query(User).filter(User.employee_id == payload.employee_id).first():
        raise HTTPException(status_code=409, detail="Employee ID already exists")
    dept = db.query(Department).filter(Department.code == payload.department_code).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    if payload.department_code == DepartmentCode.MANAGER and not (hasattr(user, "department") and user.department.code == DepartmentCode.MANAGER):
        raise HTTPException(status_code=403, detail="Only an existing Manager can create another Manager account")
    new_user = User(
        employee_id=payload.employee_id, full_name=payload.full_name, email=payload.email,
        password_hash=hash_password(payload.password), department_id=dept.id,
        is_department_admin=payload.is_department_admin, must_change_password=True, created_by=user.id if hasattr(user, "id") else None,
    )
    db.add(new_user)
    audit_service.record(db, user=user, action="USER_CREATED", entity_type="User")
    db.commit()
    db.refresh(new_user)
    return new_user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, payload: UserUpdate, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    if "department_code" in data:
        dept = db.query(Department).filter(Department.code == data.pop("department_code")).first()
        if not dept:
            raise HTTPException(status_code=404, detail="Department not found")
        target.department_id = dept.id
    for field, value in data.items():
        setattr(target, field, value)
    audit_service.record(db, user=user, action="USER_UPDATED", entity_type="User", entity_id=target.id)
    db.commit()
    db.refresh(target)
    return target


@router.post("/{user_id}/reset-password")
def reset_password(user_id: uuid.UUID, new_password: str, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.password_hash = hash_password(new_password)
    target.must_change_password = True
    audit_service.record(db, user=user, action="USER_PASSWORD_RESET", entity_type="User", entity_id=target.id)
    db.commit()
    return {"ok": True}


@router.delete("/{user_id}")
def deactivate_user(user_id: uuid.UUID, user: User = Depends(require_manager), db: Session = Depends(get_db)):
    """Soft-delete only (spec section 34) - Manager-only, not Sub-Admin."""
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.is_active = False
    audit_service.record(db, user=user, action="USER_DEACTIVATED", entity_type="User", entity_id=target.id)
    db.commit()
    return {"ok": True}
