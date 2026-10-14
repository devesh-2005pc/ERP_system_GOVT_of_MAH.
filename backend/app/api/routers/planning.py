"""
Planning Department API — core workflow enhancement.
Handles: planning dashboard, work-order assignment, machine/paper allocation,
pause/resume, production batch recording, financial year tracking.
"""
import random
import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments
from app.models.enums import (
    DepartmentCode, JobStatus, MachineStatus, PrintingMethod, PlateStatus,
    InspectionStatus,
)
from app.models.production import ProductionJob, DispatchOrder
from app.models.press_workflow import (
    Machine, PlanningAssignment, ProductionBatch, WorkOrderStatusHistory, PlateMakingRecord,
    FinishingOperation, StandardInspection, BillingRecord,
)
from app.models.material import Material
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/planning", tags=["planning"])

PLANNING_ONLY = require_departments(DepartmentCode.PLANNING)
PLANNING_OR_MANAGER = require_departments(
    DepartmentCode.PLANNING,
    DepartmentCode.MANAGER,
    DepartmentCode.SUB_ADMIN,
)
PRODUCTION_DEPTS = require_departments(
    DepartmentCode.PLANNING,
    DepartmentCode.DIGITAL_PRINTING,
    DepartmentCode.TRADITIONAL_PRINTING,
)
ANY_DEPT = get_current_user  # Any authenticated user can view work order status


# ---- Pydantic models ----

class PlanningAssignmentCreate(BaseModel):
    machine_id: Optional[uuid.UUID] = None
    paper_material_id: Optional[uuid.UUID] = None
    paper_quantity_required: Optional[Decimal] = None
    printing_method: Optional[PrintingMethod] = None
    department_code: Optional[DepartmentCode] = None
    plate_required: bool = True
    planned_start_date: Optional[datetime] = None
    planned_end_date: Optional[datetime] = None
    financial_year: Optional[str] = None
    planning_remarks: Optional[str] = None
    required_stages: Optional[list[str]] = None


class PlanningAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    machine_id: Optional[uuid.UUID] = None
    paper_material_id: Optional[uuid.UUID] = None
    paper_quantity_required: Optional[Decimal] = None
    paper_quantity_allocated: Optional[Decimal] = None
    paper_quantity_issued: Optional[Decimal] = None
    printing_method: Optional[str] = None
    department_code: Optional[str] = None
    plate_required: bool
    planned_start_date: Optional[datetime] = None
    planned_end_date: Optional[datetime] = None
    financial_year: Optional[str] = None
    is_active: bool
    pause_reason: Optional[str] = None
    paused_at: Optional[datetime] = None
    planning_remarks: Optional[str] = None


class PauseRequest(BaseModel):
    reason: str
    new_machine_id: Optional[uuid.UUID] = None


class ResumeRequest(BaseModel):
    machine_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = None


class ProductionBatchCreate(BaseModel):
    quantity_produced: int
    machine_id: Optional[uuid.UUID] = None
    department_code: Optional[DepartmentCode] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    financial_year: Optional[str] = None
    paper_quantity_used: Optional[Decimal] = None
    paper_material_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = None


class ProductionBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    batch_number: str
    quantity_produced: int
    department_code: Optional[str] = None
    machine_id: Optional[uuid.UUID] = None
    financial_year: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_complete: bool
    remarks: Optional[str] = None
    paper_quantity_used: Optional[Decimal] = None


class JobDetailOut(BaseModel):
    """Full planning view of a production job with computed quantities."""
    id: uuid.UUID
    job_number: str
    client_name: str
    work_name: str
    pages: Optional[int] = None
    copies: Optional[int] = None
    priority: str
    status: str
    deadline: Optional[datetime] = None
    created_at: datetime
    total_produced: int
    remaining_quantity: int
    total_batches: int
    current_assignment: Optional[PlanningAssignmentOut] = None
    machine_name: Optional[str] = None
    machine_code: Optional[str] = None
    machine_status: Optional[str] = None


class WorkOrderStatusHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    changed_at: datetime
    from_status: Optional[str] = None
    to_status: str
    reason: Optional[str] = None


# ---- Helper functions ----

def _get_job(db: Session, job_id: uuid.UUID) -> ProductionJob:
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Work order not found")
    return job


def _compute_produced(db: Session, job_id) -> int:
    result = db.query(func.coalesce(func.sum(ProductionBatch.quantity_produced), 0)).filter(
        ProductionBatch.job_id == job_id,
        ProductionBatch.is_complete == True,  # noqa: E712
    ).scalar()
    return int(result or 0)


def _compute_dispatched(db: Session, job_id) -> int:
    result = db.query(func.coalesce(func.sum(DispatchOrder.quantity), 0)).filter(
        DispatchOrder.job_id == job_id,
    ).scalar()
    return int(result or 0)


def _compute_current_stage(db: Session, job: ProductionJob) -> dict:
    """
    Compute the current workflow stage from actual database records.
    Returns a dict with: stage_code, stage_label, department, icon
    """
    status = job.status

    if status == JobStatus.CANCELLED:
        return {"stage_code": "CANCELLED", "stage_label": "Cancelled", "department": "-", "icon": "✗"}

    if status == JobStatus.PAUSED:
        return {"stage_code": "PAUSED", "stage_label": "Paused", "department": "Planning", "icon": "⚠"}

    # Check planning assignment
    assignment = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job.id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).order_by(PlanningAssignment.created_at.desc()).first()

    if not assignment:
        return {"stage_code": "RECEIVED", "stage_label": "Received / Awaiting Planning", "department": "Planning", "icon": "●"}

    # Check plate making
    plate_record = db.query(PlateMakingRecord).filter(PlateMakingRecord.job_id == job.id).first()
    if plate_record and not plate_record.requirement_waived:
        if plate_record.status in (PlateStatus.PENDING, PlateStatus.IN_PROGRESS):
            return {"stage_code": "PLATE_MAKING", "stage_label": "Plate Making", "department": "Plate Making", "icon": "●"}

    # Check production quantity
    total_produced = _compute_produced(db, job.id)
    ordered = job.copies or 0

    if status in (JobStatus.IN_PROGRESS, JobStatus.PARTIAL) or (total_produced < ordered and total_produced >= 0):
        dept_label = assignment.department_code.value if assignment.department_code else "Printing"
        if total_produced > 0 and total_produced < ordered:
            return {"stage_code": "PRINTING", "stage_label": f"Printing ({total_produced:,}/{ordered:,})", "department": dept_label, "icon": "●"}
        if total_produced == 0:
            return {"stage_code": "PRINTING", "stage_label": "Printing", "department": dept_label, "icon": "●"}

    if total_produced >= ordered and ordered > 0:
        # Check binding
        finishing = db.query(FinishingOperation).filter(FinishingOperation.job_id == job.id).first()
        if finishing and not finishing.is_complete:
            return {"stage_code": "BINDING", "stage_label": "Binding / Finishing", "department": "Binding", "icon": "●"}

        # Check standard inspection
        inspection = db.query(StandardInspection).filter(StandardInspection.job_id == job.id).first()
        if inspection:
            if inspection.status == InspectionStatus.REWORK_REQUIRED:
                return {"stage_code": "STANDARD", "stage_label": "Rework Required", "department": "Standard", "icon": "⚠"}
            if inspection.status in (InspectionStatus.PENDING,):
                return {"stage_code": "STANDARD", "stage_label": "Standard / Quality Check", "department": "Standard", "icon": "●"}

        # Check dispatch
        dispatched = _compute_dispatched(db, job.id)
        if dispatched < total_produced:
            return {"stage_code": "DISPATCH", "stage_label": "Dispatch", "department": "Dispatch", "icon": "●"}

        # Check billing
        bill_count = db.query(func.count(BillingRecord.id)).filter(BillingRecord.job_id == job.id).scalar() or 0
        if bill_count == 0:
            return {"stage_code": "BILLING", "stage_label": "Billing", "department": "Billing", "icon": "●"}

    if status == JobStatus.COMPLETED:
        return {"stage_code": "COMPLETED", "stage_label": "Completed", "department": "-", "icon": "✓"}

    # Fallback
    stage_map = {
        JobStatus.PLANNED: {"stage_code": "PLANNING", "stage_label": "Planning", "department": "Planning", "icon": "●"},
    }
    return stage_map.get(status, {
        "stage_code": status.value,
        "stage_label": status.value.replace("_", " ").title(),
        "department": "Planning",
        "icon": "○"
    })


def _build_workflow_stages(db: Session, job: ProductionJob) -> list:
    """Build ordered workflow stage list with status icons for display."""
    assignment = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job.id,
    ).order_by(PlanningAssignment.created_at.desc()).first()

    plate_record = db.query(PlateMakingRecord).filter(PlateMakingRecord.job_id == job.id).first()
    finishing = db.query(FinishingOperation).filter(FinishingOperation.job_id == job.id).first()
    inspection = db.query(StandardInspection).filter(StandardInspection.job_id == job.id).first()
    total_produced = _compute_produced(db, job.id)
    dispatched = _compute_dispatched(db, job.id)
    bill_count = int(db.query(func.count(BillingRecord.id)).filter(BillingRecord.job_id == job.id).scalar() or 0)
    ordered = job.copies or 0

    current_stage = _compute_current_stage(db, job)
    curr = current_stage["stage_code"]

    stages = []

    # RECEIVED
    stages.append({
        "stage": "RECEIVED", "label": "Received",
        "status": "completed", "icon": "✓",
        "date": job.created_at.strftime("%d/%m/%Y") if job.created_at else None,
        "detail": "Work order received"
    })

    # PLANNING
    if assignment:
        stages.append({
            "stage": "PLANNING", "label": "Planning",
            "status": "completed", "icon": "✓",
            "date": assignment.created_at.strftime("%d/%m/%Y") if assignment.created_at else None,
            "detail": f"Method: {assignment.printing_method.value if assignment.printing_method else '-'}"
        })
    else:
        stages.append({
            "stage": "PLANNING", "label": "Planning",
            "status": "current" if curr in ("RECEIVED", "PLANNING") else "pending",
            "icon": "●" if curr in ("RECEIVED", "PLANNING") else "○",
            "date": None, "detail": "Awaiting planning assignment"
        })

    # PLATE MAKING (only if relevant)
    if plate_record:
        if plate_record.requirement_waived:
            stages.append({"stage": "PLATE_MAKING", "label": "Plate Making", "status": "skipped", "icon": "—",
                            "date": None, "detail": "Not required"})
        elif plate_record.status == PlateStatus.COMPLETED:
            stages.append({"stage": "PLATE_MAKING", "label": "Plate Making", "status": "completed", "icon": "✓",
                            "date": plate_record.completed_at.strftime("%d/%m/%Y") if plate_record.completed_at else None,
                            "detail": f"Plates: {plate_record.plate_count or '-'}"})
        else:
            stages.append({"stage": "PLATE_MAKING", "label": "Plate Making",
                            "status": "current" if curr == "PLATE_MAKING" else "pending",
                            "icon": "●" if curr == "PLATE_MAKING" else "○",
                            "date": None, "detail": plate_record.status.value})
    elif assignment and assignment.plate_required:
        stages.append({"stage": "PLATE_MAKING", "label": "Plate Making", "status": "pending", "icon": "○",
                        "date": None, "detail": "Pending"})

    # PRINTING
    if total_produced > 0:
        pct = round(total_produced / ordered * 100) if ordered > 0 else 100
        if ordered > 0 and total_produced >= ordered:
            stages.append({"stage": "PRINTING", "label": "Printing", "status": "completed", "icon": "✓",
                            "date": None, "detail": f"{total_produced:,} / {ordered:,} copies (100%)"})
        else:
            stages.append({"stage": "PRINTING", "label": "Printing", "status": "current", "icon": "●",
                            "date": None, "detail": f"{total_produced:,} / {ordered:,} copies ({pct}%)"})
    elif assignment:
        stages.append({"stage": "PRINTING", "label": "Printing",
                        "status": "current" if curr == "PRINTING" else "pending",
                        "icon": "●" if curr == "PRINTING" else "○",
                        "date": None, "detail": "Not yet started"})

    # BINDING
    if finishing:
        if finishing.is_complete:
            stages.append({"stage": "BINDING", "label": "Binding / Finishing", "status": "completed", "icon": "✓",
                            "date": finishing.completed_at.strftime("%d/%m/%Y") if finishing.completed_at else None,
                            "detail": f"{finishing.finishing_method.value}: {finishing.quantity_completed:,}"})
        else:
            stages.append({"stage": "BINDING", "label": "Binding / Finishing",
                            "status": "current" if curr == "BINDING" else "pending",
                            "icon": "●" if curr == "BINDING" else "○",
                            "date": None,
                            "detail": f"{finishing.finishing_method.value}: {finishing.quantity_completed:,}/{finishing.quantity_received:,}"})
    else:
        stages.append({"stage": "BINDING", "label": "Binding / Finishing",
                        "status": "current" if curr == "BINDING" else "pending",
                        "icon": "●" if curr == "BINDING" else "○",
                        "date": None, "detail": "Pending"})

    # STANDARD
    if inspection:
        if inspection.status == InspectionStatus.PASSED:
            stages.append({"stage": "STANDARD", "label": "Standard / Checking", "status": "completed", "icon": "✓",
                            "date": inspection.inspected_at.strftime("%d/%m/%Y") if inspection.inspected_at else None,
                            "detail": "Inspection Passed"})
        elif inspection.status == InspectionStatus.REWORK_REQUIRED:
            stages.append({"stage": "STANDARD", "label": "Standard / Checking", "status": "blocked", "icon": "⚠",
                            "date": None, "detail": f"Rework: {inspection.rework_instructions or '-'}"})
        else:
            stages.append({"stage": "STANDARD", "label": "Standard / Checking",
                            "status": "current" if curr == "STANDARD" else "pending",
                            "icon": "●" if curr == "STANDARD" else "○",
                            "date": None, "detail": inspection.status.value})
    else:
        stages.append({"stage": "STANDARD", "label": "Standard / Checking",
                        "status": "current" if curr == "STANDARD" else "pending",
                        "icon": "●" if curr == "STANDARD" else "○",
                        "date": None, "detail": "Pending"})

    # DISPATCH
    if dispatched > 0:
        stages.append({"stage": "DISPATCH", "label": "Dispatch",
                        "status": "completed" if dispatched >= total_produced else "current",
                        "icon": "✓" if dispatched >= total_produced else "●",
                        "date": None, "detail": f"Dispatched: {dispatched:,}"})
    else:
        stages.append({"stage": "DISPATCH", "label": "Dispatch",
                        "status": "current" if curr == "DISPATCH" else "pending",
                        "icon": "●" if curr == "DISPATCH" else "○",
                        "date": None, "detail": "Pending dispatch"})

    # BILLING
    if bill_count > 0:
        stages.append({"stage": "BILLING", "label": "Billing", "status": "completed", "icon": "✓",
                        "date": None, "detail": f"Bills generated: {bill_count}"})
    else:
        stages.append({"stage": "BILLING", "label": "Billing",
                        "status": "current" if curr == "BILLING" else "pending",
                        "icon": "●" if curr == "BILLING" else "○",
                        "date": None, "detail": "Billing pending"})

    # COMPLETED
    stages.append({"stage": "COMPLETED", "label": "Completed",
                    "status": "completed" if job.status == JobStatus.COMPLETED else "pending",
                    "icon": "✓" if job.status == JobStatus.COMPLETED else "○",
                    "date": None, "detail": ""})

    return stages


def _build_job_detail(db: Session, job: ProductionJob) -> dict:
    total_produced = _compute_produced(db, job.id)
    ordered = job.copies or 0
    remaining = max(0, ordered - total_produced)
    batch_count = db.query(func.count(ProductionBatch.id)).filter(ProductionBatch.job_id == job.id).scalar()

    current_assignment = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job.id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).order_by(PlanningAssignment.created_at.desc()).first()

    machine = None
    if current_assignment and current_assignment.machine_id:
        machine = db.query(Machine).filter(Machine.id == current_assignment.machine_id).first()

    return {
        "id": job.id,
        "job_number": job.job_number,
        "client_name": job.client_name,
        "work_name": job.work_name,
        "pages": job.pages,
        "copies": job.copies,
        "priority": job.priority,
        "status": job.status.value,
        "deadline": job.deadline,
        "created_at": job.created_at,
        "total_produced": total_produced,
        "remaining_quantity": remaining,
        "total_batches": batch_count or 0,
        "current_assignment": current_assignment,
        "machine_name": machine.name if machine else None,
        "machine_code": machine.machine_code if machine else None,
        "machine_status": machine.status.value if machine else None,
    }


def _gen_batch_number(db: Session) -> str:
    suffix = "".join(random.choices(string.digits, k=7))
    return f"BTH-{suffix}"


# ---- Planning Dashboard ----

@router.get("/dashboard")
def planning_dashboard(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    financial_year: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(PLANNING_ONLY),
    db: Session = Depends(get_db),
):
    """Server-side paginated planning dashboard with summary cards."""
    total_jobs = db.query(func.count(ProductionJob.id)).scalar()
    new_unplanned = db.query(func.count(ProductionJob.id)).filter(
        ProductionJob.status == JobStatus.PLANNED,
    ).scalar()
    in_production = db.query(func.count(ProductionJob.id)).filter(
        ProductionJob.status == JobStatus.IN_PROGRESS,
    ).scalar()
    paused = db.query(func.count(ProductionJob.id)).filter(
        ProductionJob.status == JobStatus.PAUSED,
    ).scalar()
    partial = db.query(func.count(ProductionJob.id)).filter(
        ProductionJob.status == JobStatus.PARTIAL,
    ).scalar()
    available_machines = db.query(func.count(Machine.id)).filter(
        Machine.status == MachineStatus.AVAILABLE, Machine.is_active == True,  # noqa: E712
    ).scalar()

    q = db.query(ProductionJob)
    if status:
        try:
            q = q.filter(ProductionJob.status == JobStatus(status))
        except ValueError:
            pass
    if priority:
        q = q.filter(ProductionJob.priority == priority.upper())

    total = q.count()
    jobs = q.order_by(ProductionJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    job_list = []
    for job in jobs:
        total_produced = _compute_produced(db, job.id)
        ordered = job.copies or 0
        remaining = max(0, ordered - total_produced)
        current_assignment = db.query(PlanningAssignment).filter(
            PlanningAssignment.job_id == job.id,
            PlanningAssignment.is_active == True,  # noqa: E712
        ).order_by(PlanningAssignment.created_at.desc()).first()
        machine_name = None
        if current_assignment and current_assignment.machine_id:
            machine = db.query(Machine).get(current_assignment.machine_id)
            machine_name = machine.name if machine else None
        current_stage = _compute_current_stage(db, job)
        job_list.append({
            "id": str(job.id), "job_number": job.job_number,
            "client_name": job.client_name, "work_name": job.work_name,
            "copies": ordered, "priority": job.priority, "status": job.status.value,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "total_produced": total_produced, "remaining": remaining,
            "machine_name": machine_name,
            "has_assignment": current_assignment is not None,
            "current_stage": current_stage,
            "printing_method": current_assignment.printing_method.value if (current_assignment and current_assignment.printing_method) else None,
            "department": current_assignment.department_code.value if (current_assignment and current_assignment.department_code) else None,
        })

    return {
        "summary": {
            "total_work_orders": total_jobs,
            "unplanned": new_unplanned,
            "in_production": in_production,
            "paused": paused,
            "partial": partial,
            "available_machines": available_machines,
        },
        "jobs": job_list,
        "pagination": {"total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size)},
    }


# ---- Work Order List with workflow stage ----

@router.get("/jobs")
def list_jobs_with_workflow(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(PLANNING_OR_MANAGER),
    db: Session = Depends(get_db),
):
    """Paginated work orders list with current_stage computed from DB."""
    q = db.query(ProductionJob)
    if status:
        try:
            q = q.filter(ProductionJob.status == JobStatus(status))
        except ValueError:
            pass
    if priority:
        q = q.filter(ProductionJob.priority == priority.upper())
    if search:
        q = q.filter(
            (ProductionJob.job_number.ilike(f"%{search}%")) |
            (ProductionJob.client_name.ilike(f"%{search}%")) |
            (ProductionJob.work_name.ilike(f"%{search}%"))
        )

    total = q.count()
    jobs = q.order_by(ProductionJob.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    job_list = []
    for job in jobs:
        total_produced = _compute_produced(db, job.id)
        ordered = job.copies or 0
        remaining = max(0, ordered - total_produced)
        pct = round(total_produced / ordered * 100) if ordered > 0 else 0
        current_assignment = db.query(PlanningAssignment).filter(
            PlanningAssignment.job_id == job.id,
            PlanningAssignment.is_active == True,  # noqa: E712
        ).order_by(PlanningAssignment.created_at.desc()).first()
        machine_name = None
        machine_code = None
        if current_assignment and current_assignment.machine_id:
            machine = db.query(Machine).get(current_assignment.machine_id)
            if machine:
                machine_name = machine.name
                machine_code = machine.machine_code
        current_stage = _compute_current_stage(db, job)
        job_list.append({
            "id": str(job.id),
            "job_number": job.job_number,
            "client_name": job.client_name,
            "work_name": job.work_name,
            "copies": ordered,
            "total_produced": total_produced,
            "remaining": remaining,
            "progress_pct": pct,
            "priority": job.priority,
            "status": job.status.value,
            "deadline": job.deadline.isoformat() if job.deadline else None,
            "current_stage": current_stage,
            "machine_name": machine_name,
            "machine_code": machine_code,
            "department": current_assignment.department_code.value if (current_assignment and current_assignment.department_code) else None,
            "printing_method": current_assignment.printing_method.value if (current_assignment and current_assignment.printing_method) else None,
            "has_assignment": current_assignment is not None,
            "paused": job.status == JobStatus.PAUSED,
            "pause_reason": current_assignment.pause_reason if current_assignment else None,
        })

    return {
        "jobs": job_list,
        "pagination": {"total": total, "page": page, "page_size": page_size, "pages": -(-total // page_size)},
    }


# ---- Full Workflow Detail for a Job ----

@router.get("/jobs/{job_id}/detail")
def get_job_workflow_detail(
    job_id: uuid.UUID,
    user: User = Depends(ANY_DEPT),
    db: Session = Depends(get_db),
):
    """Full workflow detail — all stages, quantities, history."""
    job = _get_job(db, job_id)

    total_produced = _compute_produced(db, job.id)
    dispatched = _compute_dispatched(db, job.id)
    ordered = job.copies or 0
    remaining = max(0, ordered - total_produced)
    pct = round(total_produced / ordered * 100) if ordered > 0 else 0

    current_assignment = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job.id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).order_by(PlanningAssignment.created_at.desc()).first()

    machine = None
    paper_material = None
    if current_assignment:
        if current_assignment.machine_id:
            machine = db.query(Machine).filter(Machine.id == current_assignment.machine_id).first()
        if current_assignment.paper_material_id:
            paper_material = db.query(Material).filter(Material.id == current_assignment.paper_material_id).first()

    batches = db.query(ProductionBatch).filter(
        ProductionBatch.job_id == job.id
    ).order_by(ProductionBatch.created_at.desc()).all()

    plate_record = db.query(PlateMakingRecord).filter(PlateMakingRecord.job_id == job.id).first()
    finishing = db.query(FinishingOperation).filter(FinishingOperation.job_id == job.id).first()
    inspection = db.query(StandardInspection).filter(StandardInspection.job_id == job.id).first()
    bills = db.query(BillingRecord).filter(BillingRecord.job_id == job.id).order_by(BillingRecord.generated_at.desc()).all()
    history = db.query(WorkOrderStatusHistory).filter(
        WorkOrderStatusHistory.job_id == job.id
    ).order_by(WorkOrderStatusHistory.changed_at.asc()).all()

    current_stage = _compute_current_stage(db, job)
    workflow_stages = _build_workflow_stages(db, job)

    stage_order = ["RECEIVED", "PLANNING", "PLATE_MAKING", "PRINTING", "BINDING", "STANDARD", "DISPATCH", "BILLING", "COMPLETED"]
    current_idx = next((i for i, s in enumerate(stage_order) if s == current_stage["stage_code"]), 0)
    next_stage = stage_order[current_idx + 1] if current_idx + 1 < len(stage_order) else None

    return {
        "id": str(job.id),
        "job_number": job.job_number,
        "client_name": job.client_name,
        "work_name": job.work_name,
        "pages": job.pages,
        "copies": ordered,
        "priority": job.priority,
        "status": job.status.value,
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "total_produced": total_produced,
        "remaining_quantity": remaining,
        "dispatched_quantity": dispatched,
        "progress_pct": pct,
        "total_batches": len(batches),
        "current_stage": current_stage,
        "next_stage": next_stage,
        "workflow_stages": workflow_stages,
        "planning": {
            "machine_id": str(current_assignment.machine_id) if (current_assignment and current_assignment.machine_id) else None,
            "machine_name": machine.name if machine else None,
            "machine_code": machine.machine_code if machine else None,
            "machine_status": machine.status.value if machine else None,
            "printing_method": current_assignment.printing_method.value if (current_assignment and current_assignment.printing_method) else None,
            "department": current_assignment.department_code.value if (current_assignment and current_assignment.department_code) else None,
            "paper_name": paper_material.name if paper_material else None,
            "paper_gsm": paper_material.gsm if paper_material else None,
            "paper_quantity_required": float(current_assignment.paper_quantity_required) if (current_assignment and current_assignment.paper_quantity_required) else None,
            "paper_quantity_allocated": float(current_assignment.paper_quantity_allocated) if (current_assignment and current_assignment.paper_quantity_allocated) else None,
            "plate_required": current_assignment.plate_required if current_assignment else None,
            "planned_start": current_assignment.planned_start_date.isoformat() if (current_assignment and current_assignment.planned_start_date) else None,
            "planned_end": current_assignment.planned_end_date.isoformat() if (current_assignment and current_assignment.planned_end_date) else None,
            "financial_year": current_assignment.financial_year if current_assignment else None,
            "remarks": current_assignment.planning_remarks if current_assignment else None,
            "paused": job.status == JobStatus.PAUSED,
            "pause_reason": current_assignment.pause_reason if current_assignment else None,
        } if current_assignment else None,
        "plate_making": {
            "id": str(plate_record.id),
            "status": plate_record.status.value,
            "plate_count": plate_record.plate_count,
            "plate_size": plate_record.plate_size,
            "requirement_waived": plate_record.requirement_waived,
            "waiver_reason": plate_record.waiver_reason,
            "started_at": plate_record.started_at.isoformat() if plate_record.started_at else None,
            "completed_at": plate_record.completed_at.isoformat() if plate_record.completed_at else None,
            "remarks": plate_record.remarks,
        } if plate_record else None,
        "batches": [{
            "id": str(b.id),
            "batch_number": b.batch_number,
            "quantity_produced": b.quantity_produced,
            "department": b.department_code.value if b.department_code else None,
            "financial_year": b.financial_year,
            "started_at": b.started_at.isoformat() if b.started_at else None,
            "completed_at": b.completed_at.isoformat() if b.completed_at else None,
            "is_complete": b.is_complete,
            "remarks": b.remarks,
        } for b in batches],
        "finishing": {
            "id": str(finishing.id),
            "method": finishing.finishing_method.value,
            "quantity_received": finishing.quantity_received,
            "quantity_completed": finishing.quantity_completed,
            "quantity_pending": finishing.quantity_pending,
            "is_complete": finishing.is_complete,
            "started_at": finishing.started_at.isoformat() if finishing.started_at else None,
            "completed_at": finishing.completed_at.isoformat() if finishing.completed_at else None,
            "remarks": finishing.remarks,
        } if finishing else None,
        "inspection": {
            "id": str(inspection.id),
            "status": inspection.status.value,
            "quantity_inspected": inspection.quantity_inspected,
            "packaging_ok": inspection.packaging_ok,
            "quantity_ok": inspection.quantity_ok,
            "remarks": inspection.inspection_remarks,
            "rework_instructions": inspection.rework_instructions,
            "inspected_at": inspection.inspected_at.isoformat() if inspection.inspected_at else None,
        } if inspection else None,
        "billing": {
            "total_billed": sum(b.billing_quantity or 0 for b in bills),
            "bill_count": len(bills),
            "records": [{
                "id": str(b.id),
                "bill_reference": b.bill_reference,
                "billing_quantity": b.billing_quantity,
                "status": b.status.value,
                "generated_at": b.generated_at.isoformat() if b.generated_at else None,
            } for b in bills],
        },
        "dispatch_quantity": dispatched,
        "workflow_history": [{
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
            "from_status": h.from_status,
            "to_status": h.to_status,
            "reason": h.reason,
        } for h in history],
    }


# ---- Original detail endpoint (kept for backward compatibility) ----

@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def get_job_planning_detail(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_MANAGER), db: Session = Depends(get_db)):
    job = _get_job(db, job_id)
    return _build_job_detail(db, job)


# ---- Assign / Re-assign ----

@router.post("/jobs/{job_id}/assign", response_model=PlanningAssignmentOut, status_code=201)
async def assign_job(
    job_id: uuid.UUID,
    payload: PlanningAssignmentCreate,
    user: User = Depends(PLANNING_ONLY),
    db: Session = Depends(get_db),
):
    """Assign or re-assign a work order to a machine/dept. Previous assignment deactivated."""
    job = _get_job(db, job_id)

    if payload.machine_id:
        machine = db.query(Machine).filter(Machine.id == payload.machine_id).first()
        if not machine:
            raise HTTPException(status_code=404, detail="Machine not found")
        if machine.status not in (MachineStatus.AVAILABLE, MachineStatus.ASSIGNED):
            raise HTTPException(
                status_code=400,
                detail=f"Machine {machine.name} is not available (status: {machine.status.value})"
            )
        machine.status = MachineStatus.ASSIGNED
        machine.updated_by = user.id

    db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job_id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).update({"is_active": False}, synchronize_session=False)

    assignment = PlanningAssignment(
        job_id=job_id,
        machine_id=payload.machine_id,
        assigned_by=user.id,
        paper_material_id=payload.paper_material_id,
        paper_quantity_required=payload.paper_quantity_required,
        printing_method=payload.printing_method,
        department_code=payload.department_code,
        plate_required=payload.plate_required,
        planned_start_date=payload.planned_start_date,
        planned_end_date=payload.planned_end_date,
        financial_year=payload.financial_year,
        planning_remarks=payload.planning_remarks,
        is_active=True,
        created_by=user.id,
    )
    db.add(assignment)

    if payload.plate_required:
        existing_plate = db.query(PlateMakingRecord).filter(
            PlateMakingRecord.job_id == job_id
        ).first()
        if not existing_plate:
            db.add(PlateMakingRecord(job_id=job_id, status=PlateStatus.PENDING, created_by=user.id))

    old_status = job.status.value
    if job.status == JobStatus.PLANNED:
        job.status = JobStatus.IN_PROGRESS
        job.updated_by = user.id

    db.add(WorkOrderStatusHistory(
        job_id=job_id,
        changed_by=user.id,
        from_status=old_status,
        to_status=job.status.value,
        reason=f"Planning assignment: Machine={payload.machine_id}, Method={payload.printing_method.value if payload.printing_method else 'not set'}",
        machine_id=payload.machine_id,
    ))

    audit_service.record(
        db, user=user, action="JOB_PLANNING_ASSIGNED", entity_type="ProductionJob", entity_id=job_id,
        detail=f"Machine: {payload.machine_id}, Dept: {payload.department_code}",
    )
    db.commit()
    db.refresh(assignment)

    await manager.broadcast(
        "JOB_ASSIGNED",
        {"job_id": str(job_id), "job_number": job.job_number,
         "machine_id": str(payload.machine_id) if payload.machine_id else None},
        visible_to_departments={
            DepartmentCode.PLANNING.value, DepartmentCode.DIGITAL_PRINTING.value,
            DepartmentCode.TRADITIONAL_PRINTING.value
        },
    )
    return assignment


# ---- Pause ----

@router.post("/jobs/{job_id}/pause", response_model=PlanningAssignmentOut)
async def pause_job(
    job_id: uuid.UUID,
    payload: PauseRequest,
    user: User = Depends(PLANNING_ONLY),
    db: Session = Depends(get_db),
):
    job = _get_job(db, job_id)
    if job.status not in (JobStatus.IN_PROGRESS, JobStatus.PLANNED, JobStatus.PARTIAL):
        raise HTTPException(status_code=400, detail=f"Cannot pause job in status {job.status.value}")

    current = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job_id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).order_by(PlanningAssignment.created_at.desc()).first()

    old_status = job.status.value
    job.status = JobStatus.PAUSED
    job.updated_by = user.id

    if current and current.machine_id:
        machine = db.query(Machine).filter(Machine.id == current.machine_id).first()
        if machine:
            machine.status = MachineStatus.AVAILABLE
            machine.updated_by = user.id

    if current:
        current.pause_reason = payload.reason
        current.paused_at = datetime.utcnow()
        if payload.new_machine_id:
            current.machine_id = payload.new_machine_id

    db.add(WorkOrderStatusHistory(
        job_id=job_id, changed_by=user.id, from_status=old_status,
        to_status=JobStatus.PAUSED.value, reason=payload.reason,
    ))
    audit_service.record(db, user=user, action="JOB_PAUSED", entity_type="ProductionJob", entity_id=job_id, detail=payload.reason)
    db.commit()
    if current:
        db.refresh(current)

    await manager.broadcast(
        "JOB_PAUSED",
        {"job_id": str(job_id), "job_number": job.job_number, "reason": payload.reason},
        visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.DIGITAL_PRINTING.value, DepartmentCode.TRADITIONAL_PRINTING.value},
    )
    return current


# ---- Resume ----

@router.post("/jobs/{job_id}/resume", response_model=PlanningAssignmentOut)
async def resume_job(
    job_id: uuid.UUID,
    payload: ResumeRequest,
    user: User = Depends(PLANNING_ONLY),
    db: Session = Depends(get_db),
):
    job = _get_job(db, job_id)
    if job.status != JobStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Job is not paused")

    current = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job_id,
        PlanningAssignment.is_active == True,  # noqa: E712
    ).order_by(PlanningAssignment.created_at.desc()).first()

    target_machine_id = payload.machine_id or (current.machine_id if current else None)
    if target_machine_id:
        machine = db.query(Machine).filter(Machine.id == target_machine_id).first()
        if machine and machine.status not in (MachineStatus.AVAILABLE, MachineStatus.ASSIGNED):
            raise HTTPException(status_code=400, detail=f"Machine {machine.name} is not available")
        if machine:
            machine.status = MachineStatus.ASSIGNED
            machine.updated_by = user.id

    old_status = job.status.value
    total_produced = _compute_produced(db, job.id)
    ordered = job.copies or 0
    if total_produced > 0 and total_produced < ordered:
        job.status = JobStatus.PARTIAL
    elif total_produced >= ordered and ordered > 0:
        job.status = JobStatus.COMPLETED
    else:
        job.status = JobStatus.IN_PROGRESS

    if current:
        current.resumed_at = datetime.utcnow()
        current.pause_reason = None
        if payload.machine_id:
            current.machine_id = payload.machine_id

    db.add(WorkOrderStatusHistory(
        job_id=job_id, changed_by=user.id, from_status=old_status,
        to_status=job.status.value, reason=payload.remarks or "Job resumed",
        machine_id=target_machine_id,
    ))
    audit_service.record(db, user=user, action="JOB_RESUMED", entity_type="ProductionJob", entity_id=job_id)
    db.commit()
    if current:
        db.refresh(current)

    await manager.broadcast(
        "JOB_RESUMED",
        {"job_id": str(job_id), "job_number": job.job_number},
        visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.DIGITAL_PRINTING.value, DepartmentCode.TRADITIONAL_PRINTING.value},
    )
    return current


# ---- Production Batches ----

@router.get("/jobs/{job_id}/batches", response_model=list[ProductionBatchOut])
def list_batches(job_id: uuid.UUID, user: User = Depends(PRODUCTION_DEPTS), db: Session = Depends(get_db)):
    _get_job(db, job_id)
    return db.query(ProductionBatch).filter(ProductionBatch.job_id == job_id).order_by(ProductionBatch.created_at.desc()).all()


@router.post("/jobs/{job_id}/batches", response_model=ProductionBatchOut, status_code=201)
async def record_production_batch(
    job_id: uuid.UUID,
    payload: ProductionBatchCreate,
    user: User = Depends(PRODUCTION_DEPTS),
    db: Session = Depends(get_db),
):
    """Record a production batch. Validates that quantity does not exceed authorized remaining."""
    job = _get_job(db, job_id)
    if job.status == JobStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Cannot record production for a cancelled job")
    if job.status == JobStatus.PAUSED:
        raise HTTPException(status_code=400, detail="Job is paused. Resume before recording production")
    if job.status == JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job is already production-complete")

    if payload.quantity_produced <= 0:
        raise HTTPException(status_code=400, detail="Quantity produced must be positive")

    total_produced = _compute_produced(db, job_id)
    ordered = job.copies or 0
    if ordered > 0 and (total_produced + payload.quantity_produced) > ordered:
        raise HTTPException(
            status_code=400,
            detail=f"Batch {payload.quantity_produced} would exceed ordered {ordered}. "
                   f"Already produced: {total_produced}, Remaining: {ordered - total_produced}",
        )

    batch_number = _gen_batch_number(db)
    batch = ProductionBatch(
        job_id=job_id,
        machine_id=payload.machine_id,
        department_code=payload.department_code or user.department.code,
        operator_id=user.id,
        batch_number=batch_number,
        quantity_produced=payload.quantity_produced,
        financial_year=payload.financial_year,
        started_at=payload.started_at or datetime.utcnow(),
        completed_at=payload.completed_at or datetime.utcnow(),
        is_complete=True,
        remarks=payload.remarks,
        paper_quantity_used=payload.paper_quantity_used,
        paper_material_id=payload.paper_material_id,
        created_by=user.id,
    )
    db.add(batch)

    new_total = total_produced + payload.quantity_produced
    old_status = job.status.value
    if ordered > 0 and new_total >= ordered:
        job.status = JobStatus.COMPLETED
    elif new_total > 0:
        job.status = JobStatus.IN_PROGRESS
    else:
        job.status = JobStatus.IN_PROGRESS

    if old_status == JobStatus.PLANNED.value:
        job.status = JobStatus.IN_PROGRESS if (ordered == 0 or new_total < ordered) else JobStatus.COMPLETED

    db.add(WorkOrderStatusHistory(
        job_id=job_id, changed_by=user.id, from_status=old_status,
        to_status=job.status.value,
        reason=f"Production batch {batch_number}: {payload.quantity_produced:,} copies printed",
        machine_id=payload.machine_id,
    ))
    audit_service.record(
        db, user=user, action="PRODUCTION_BATCH_RECORDED", entity_type="ProductionBatch", entity_id=batch.id,
        detail=f"Job: {job.job_number}, Qty: {payload.quantity_produced}",
    )
    db.commit()
    db.refresh(batch)

    await manager.broadcast(
        "PRODUCTION_UPDATED",
        {"job_id": str(job_id), "job_number": job.job_number, "batch_number": batch_number,
         "qty": payload.quantity_produced, "total_produced": new_total, "remaining": max(0, ordered - new_total)},
        visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.DISPATCH.value},
    )
    return batch


# ---- Status History ----

@router.get("/jobs/{job_id}/history", response_model=list[WorkOrderStatusHistoryOut])
def get_status_history(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_MANAGER), db: Session = Depends(get_db)):
    _get_job(db, job_id)
    from app.models.press_workflow import WorkOrderStatusHistory as WSH
    return db.query(WSH).filter(WSH.job_id == job_id).order_by(WSH.changed_at.desc()).all()
