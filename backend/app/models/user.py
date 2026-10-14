from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, SoftDeleteMixin, GUID, gen_uuid
from app.models.enums import DepartmentCode


class Department(Base, IDMixin, TimestampMixin):
    __tablename__ = "departments"

    code = Column(SAEnum(DepartmentCode), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    description = Column(String(500), nullable=True)

    users = relationship("User", back_populates="department")


class User(Base, IDMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    employee_id = Column(String(50), unique=True, nullable=False, index=True)
    full_name = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=True)
    password_hash = Column(String(255), nullable=False)

    department_id = Column(GUID(), ForeignKey("departments.id"), nullable=False)
    department = relationship("Department", back_populates="users")

    # A user with is_department_admin=True (only meaningful for SUB_ADMIN dept
    # users) has elevated but still-restricted permissions; see rbac.py.
    is_department_admin = Column(Boolean, default=False, nullable=False)

    must_change_password = Column(Boolean, default=True, nullable=False)
    mfa_enabled = Column(Boolean, default=False, nullable=False)
    mfa_secret = Column(String(64), nullable=True)

    failed_login_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    def __repr__(self):
        return f"<User {self.employee_id} dept={self.department_id}>"


class RefreshSession(Base, IDMixin, TimestampMixin):
    """Server-side session record backing refresh tokens, so sessions can be
    revoked (logout, admin-forced logout, idle timeout) rather than relying
    purely on unverifiable stateless JWTs."""
    __tablename__ = "refresh_sessions"

    id = Column(GUID(), primary_key=True, default=gen_uuid)
    user_id = Column(GUID(), ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)

    def is_valid(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.utcnow()


class LoginHistory(Base, IDMixin):
    __tablename__ = "login_history"

    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True, index=True)
    employee_id_attempted = Column(String(50), nullable=False)
    success = Column(Boolean, nullable=False)
    reason = Column(String(120), nullable=True)
    ip_address = Column(String(64), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
