import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Boolean, String
from sqlalchemy.types import TypeDecorator, CHAR

from app.core.database import Base


class GUID(TypeDecorator):
    """Platform-independent UUID column: stores as CHAR(36) so it works
    identically on SQLite (dev) and PostgreSQL (prod) without requiring the
    native PG UUID type everywhere."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return uuid.UUID(value)


def gen_uuid():
    return str(uuid.uuid4())


class IDMixin:
    id = Column(GUID(), primary_key=True, default=gen_uuid)


class TimestampMixin:
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class AuditMixin:
    created_by = Column(GUID(), nullable=True)
    updated_by = Column(GUID(), nullable=True)


class SoftDeleteMixin:
    is_active = Column(Boolean, default=True, nullable=False)
    deleted_at = Column(DateTime, nullable=True)
