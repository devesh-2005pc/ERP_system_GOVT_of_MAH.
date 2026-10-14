from sqlalchemy import Column, String, Numeric, ForeignKey, Enum as SAEnum, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, GUID
from app.models.enums import RequestStatus, DepartmentCode


class MaterialRequest(Base, IDMixin, TimestampMixin, AuditMixin):
    """Requesting department owns/sees its own requests; STORE (fulfiller)
    and MANAGER/SUB_ADMIN see all requests, per the cross-department rule."""
    __tablename__ = "material_requests"

    request_no = Column(String(30), unique=True, nullable=False)
    requesting_department_id = Column(GUID(), ForeignKey("departments.id"), nullable=False)
    requested_by = Column(GUID(), ForeignKey("users.id"), nullable=False)
    reason = Column(String(500), nullable=True)
    priority = Column(String(20), nullable=False, default="NORMAL")  # LOW/NORMAL/HIGH/URGENT
    status = Column(SAEnum(RequestStatus), nullable=False, default=RequestStatus.SUBMITTED)

    items = relationship("MaterialRequestItem", back_populates="request", cascade="all, delete-orphan")
    approvals = relationship("RequestApproval", back_populates="request", cascade="all, delete-orphan")


class MaterialRequestItem(Base, IDMixin):
    __tablename__ = "material_request_items"

    request_id = Column(GUID(), ForeignKey("material_requests.id"), nullable=False)
    material_id = Column(GUID(), ForeignKey("materials.id"), nullable=False)
    quantity_requested = Column(Numeric(14, 3), nullable=False)
    quantity_fulfilled = Column(Numeric(14, 3), nullable=False, default=0)

    request = relationship("MaterialRequest", back_populates="items")
    material = relationship("Material")


class RequestApproval(Base, IDMixin, TimestampMixin):
    __tablename__ = "request_approvals"

    request_id = Column(GUID(), ForeignKey("material_requests.id"), nullable=False)
    approver_id = Column(GUID(), ForeignKey("users.id"), nullable=False)
    decision = Column(String(20), nullable=False)  # APPROVED / REJECTED
    comments = Column(String(500), nullable=True)

    request = relationship("MaterialRequest", back_populates="approvals")
