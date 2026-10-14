from datetime import datetime

from sqlalchemy import Column, String, ForeignKey, Boolean, DateTime, Text, JSON
from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, GUID


class Notification(Base, IDMixin, TimestampMixin):
    __tablename__ = "notifications"

    user_id = Column(GUID(), ForeignKey("users.id"), nullable=True, index=True)
    department_id = Column(GUID(), ForeignKey("departments.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(String(500), nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    payload = Column(JSON, nullable=True)


class AuditLog(Base, IDMixin):
    """Immutable append-only audit trail. Manager-only read access."""
    __tablename__ = "audit_logs"

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_id = Column(GUID(), nullable=True, index=True)
    employee_id = Column(String(50), nullable=True)
    department_code = Column(String(30), nullable=True)
    action = Column(String(80), nullable=False, index=True)
    entity_type = Column(String(80), nullable=True)
    entity_id = Column(GUID(), nullable=True)
    before_state = Column(JSON, nullable=True)
    after_state = Column(JSON, nullable=True)
    ip_address = Column(String(64), nullable=True)
    detail = Column(Text, nullable=True)


class Device(Base, IDMixin, TimestampMixin):
    """Devices activated against this office's license."""
    __tablename__ = "devices"

    device_fingerprint = Column(String(128), unique=True, nullable=False)
    computer_name = Column(String(150), nullable=True)
    department_id = Column(GUID(), ForeignKey("departments.id"), nullable=True)
    status = Column(String(20), nullable=False, default="ACTIVE")  # ACTIVE / REVOKED
    activated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at = Column(DateTime, nullable=True)


class SystemSetting(Base, IDMixin, TimestampMixin):
    __tablename__ = "system_settings"
    key = Column(String(100), unique=True, nullable=False)
    value = Column(Text, nullable=True)
