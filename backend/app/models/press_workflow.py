"""
Press workflow enhancement models - additive new tables, existing tables unchanged.
"""
from datetime import datetime
from sqlalchemy import Column, String, Numeric, ForeignKey, Enum as SAEnum, DateTime, Integer, Text, Boolean
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, GUID
from app.models.enums import (
    MachineStatus, PrintingMethod, PlateStatus,
    FinishingMethod, InspectionStatus, BillingStatus, MaintenanceStatus, DepartmentCode,
)


class Machine(Base, IDMixin, TimestampMixin, AuditMixin):
    """Physical printing/finishing machine master."""
    __tablename__ = "machines"
    machine_code = Column(String(30), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    machine_type = Column(String(100), nullable=True)
    printing_method = Column(SAEnum(PrintingMethod), nullable=True)
    department_code = Column(SAEnum(DepartmentCode), nullable=True)
    location = Column(String(150), nullable=True)
    max_paper_size = Column(String(50), nullable=True)
    min_paper_size = Column(String(50), nullable=True)
    supported_gsm_range = Column(String(50), nullable=True)
    max_impressions_per_hour = Column(Integer, nullable=True)
    is_color = Column(Boolean, default=False, nullable=False)
    remarks = Column(Text, nullable=True)
    status = Column(SAEnum(MachineStatus), nullable=False, default=MachineStatus.AVAILABLE)
    is_active = Column(Boolean, default=True, nullable=False)
    maintenance_records = relationship("MachineMaintenance", back_populates="machine")
    planning_assignments = relationship("PlanningAssignment", back_populates="machine")
    production_batches = relationship("ProductionBatch", back_populates="machine")


class MachineMaintenance(Base, IDMixin, TimestampMixin, AuditMixin):
    """Machine breakdown/maintenance records."""
    __tablename__ = "machine_maintenance"
    machine_id = Column(GUID(), ForeignKey("machines.id"), nullable=False, index=True)
    reported_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    assigned_mechanic_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    issue_description = Column(Text, nullable=False)
    reported_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(SAEnum(MaintenanceStatus), nullable=False, default=MaintenanceStatus.REPORTED)
    repair_remarks = Column(Text, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    machine = relationship("Machine", back_populates="maintenance_records")


class PlanningAssignment(Base, IDMixin, TimestampMixin, AuditMixin):
    """Planning decisions: machine, paper, priority, dates for a work order."""
    __tablename__ = "planning_assignments"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    machine_id = Column(GUID(), ForeignKey("machines.id"), nullable=True)
    assigned_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    paper_material_id = Column(GUID(), ForeignKey("materials.id"), nullable=True)
    paper_quantity_required = Column(Numeric(14, 3), nullable=True)
    paper_quantity_allocated = Column(Numeric(14, 3), nullable=True, default=0)
    paper_quantity_issued = Column(Numeric(14, 3), nullable=True, default=0)
    printing_method = Column(SAEnum(PrintingMethod), nullable=True)
    department_code = Column(SAEnum(DepartmentCode), nullable=True)
    plate_required = Column(Boolean, default=True, nullable=False)
    planned_start_date = Column(DateTime, nullable=True)
    planned_end_date = Column(DateTime, nullable=True)
    financial_year = Column(String(10), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    pause_reason = Column(Text, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    resumed_at = Column(DateTime, nullable=True)
    planning_remarks = Column(Text, nullable=True)
    job = relationship("ProductionJob")
    machine = relationship("Machine", back_populates="planning_assignments")
    paper_material = relationship("Material", foreign_keys=[paper_material_id])


class ProductionBatch(Base, IDMixin, TimestampMixin, AuditMixin):
    """Individual production run against a work order (partial/multi-year)."""
    __tablename__ = "production_batches"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    machine_id = Column(GUID(), ForeignKey("machines.id"), nullable=True)
    department_code = Column(SAEnum(DepartmentCode), nullable=True)
    operator_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    batch_number = Column(String(30), nullable=False, unique=True)
    quantity_produced = Column(Integer, nullable=False)
    financial_year = Column(String(10), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    is_complete = Column(Boolean, default=False, nullable=False)
    remarks = Column(Text, nullable=True)
    paper_quantity_used = Column(Numeric(14, 3), nullable=True)
    paper_material_id = Column(GUID(), ForeignKey("materials.id"), nullable=True)
    job = relationship("ProductionJob")
    machine = relationship("Machine", back_populates="production_batches")
    paper_material = relationship("Material", foreign_keys=[paper_material_id])


class WorkOrderStatusHistory(Base, IDMixin):
    """Append-only status change log for production jobs."""
    __tablename__ = "work_order_status_history"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    changed_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    machine_id = Column(GUID(), ForeignKey("machines.id"), nullable=True)
    job = relationship("ProductionJob")


class PlateMakingRecord(Base, IDMixin, TimestampMixin, AuditMixin):
    """CTP/plate preparation for a production job."""
    __tablename__ = "plate_making_records"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    operator_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    plate_count = Column(Integer, nullable=True)
    plate_size = Column(String(50), nullable=True)
    status = Column(SAEnum(PlateStatus), nullable=False, default=PlateStatus.PENDING)
    requirement_waived = Column(Boolean, default=False, nullable=False)
    waived_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    waiver_reason = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    remarks = Column(Text, nullable=True)
    job = relationship("ProductionJob")


class FinishingOperation(Base, IDMixin, TimestampMixin, AuditMixin):
    """Binding/finishing stage for a production job."""
    __tablename__ = "finishing_operations"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    operator_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    finishing_method = Column(SAEnum(FinishingMethod), nullable=False, default=FinishingMethod.NONE)
    quantity_received = Column(Integer, nullable=False, default=0)
    quantity_completed = Column(Integer, nullable=False, default=0)
    quantity_pending = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    remarks = Column(Text, nullable=True)
    is_complete = Column(Boolean, default=False, nullable=False)
    job = relationship("ProductionJob")


class StandardInspection(Base, IDMixin, TimestampMixin, AuditMixin):
    """Quality/packaging inspection before dispatch."""
    __tablename__ = "standard_inspections"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    inspector_id = Column(GUID(), ForeignKey("users.id"), nullable=True)
    quantity_inspected = Column(Integer, nullable=True)
    status = Column(SAEnum(InspectionStatus), nullable=False, default=InspectionStatus.PENDING)
    packaging_ok = Column(Boolean, nullable=True)
    quantity_ok = Column(Boolean, nullable=True)
    inspection_remarks = Column(Text, nullable=True)
    rework_instructions = Column(Text, nullable=True)
    inspected_at = Column(DateTime, nullable=True)
    job = relationship("ProductionJob")


class BillingRecord(Base, IDMixin, TimestampMixin, AuditMixin):
    """Bill generated against a work order by the BILLING department."""
    __tablename__ = "billing_records"
    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=False, index=True)
    bill_reference = Column(String(50), unique=True, nullable=False)
    generated_by = Column(GUID(), ForeignKey("users.id"), nullable=True)
    billing_quantity = Column(Integer, nullable=True)
    billing_amount = Column(Numeric(14, 2), nullable=True)
    status = Column(SAEnum(BillingStatus), nullable=False, default=BillingStatus.PENDING)
    cost_estimate_id = Column(GUID(), ForeignKey("cost_estimates.id"), nullable=True)
    file_path = Column(String(500), nullable=True)
    remarks = Column(Text, nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    job = relationship("ProductionJob")
