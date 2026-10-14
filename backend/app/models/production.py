from sqlalchemy import Column, String, Numeric, ForeignKey, Enum as SAEnum, DateTime, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, GUID
from app.models.enums import JobStatus, DispatchStatus


class ProductionJob(Base, IDMixin, TimestampMixin, AuditMixin):
    """PLANNING department only (+ MANAGER/SUB_ADMIN)."""
    __tablename__ = "production_jobs"

    job_number = Column(String(30), unique=True, nullable=False)
    client_name = Column(String(200), nullable=False)
    work_name = Column(String(300), nullable=False)
    pages = Column(Integer, nullable=True)
    copies = Column(Integer, nullable=True)
    priority = Column(String(20), nullable=False, default="NORMAL")
    deadline = Column(DateTime, nullable=True)
    status = Column(SAEnum(JobStatus), nullable=False, default=JobStatus.PLANNED)

    materials = relationship("ProductionJobMaterial", back_populates="job", cascade="all, delete-orphan")


class ProductionJobMaterial(Base, IDMixin):
    __tablename__ = "production_job_materials"

    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False)
    material_id = Column(GUID(), ForeignKey("materials.id"), nullable=False)
    quantity_required = Column(Numeric(14, 3), nullable=False)
    quantity_consumed = Column(Numeric(14, 3), nullable=False, default=0)

    job = relationship("ProductionJob", back_populates="materials")
    material = relationship("Material")


class DispatchOrder(Base, IDMixin, TimestampMixin, AuditMixin):
    """DISPATCH department only (+ MANAGER/SUB_ADMIN)."""
    __tablename__ = "dispatch_orders"

    dispatch_no = Column(String(30), unique=True, nullable=False)
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=True)
    recipient = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False)
    vehicle_or_courier = Column(String(150), nullable=True)
    dispatch_date = Column(DateTime, nullable=True)
    status = Column(SAEnum(DispatchStatus), nullable=False, default=DispatchStatus.PENDING)
    remarks = Column(String(500), nullable=True)
