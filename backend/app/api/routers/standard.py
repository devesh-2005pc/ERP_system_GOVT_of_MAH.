"""
Standard/QC Inspection API — STANDARD department approves before dispatch.
Dispatch cannot proceed without a PASSED inspection.
"""
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import require_departments
from app.models.enums import DepartmentCode, InspectionStatus
from app.models.press_workflow import StandardInspection
from app.models.production import ProductionJob
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/standard", tags=["standard"])

STANDARD_DEPT = require_departments(DepartmentCode.STANDARD)
PLANNING_OR_ABOVE = require_departments(DepartmentCode.PLANNING, DepartmentCode.STANDARD, DepartmentCode.DISPATCH)


class InspectionCreate(BaseModel):
    quantity_inspected: Optional[int] = None
    packaging_ok: Optional[bool] = None
    quantity_ok: Optional[bool] = None
    inspection_remarks: Optional[str] = None
    rework_instructions: Optional[str] = None


class InspectionDecision(BaseModel):
    status: InspectionStatus
    inspection_remarks: Optional[str] = None
    rework_instructions: Optional[str] = None
    quantity_inspected: Optional[int] = None
    packaging_ok: Optional[bool] = None
    quantity_ok: Optional[bool] = None


class InspectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    quantity_inspected: Optional[int] = None
    status: str
    packaging_ok: Optional[bool] = None
    quantity_ok: Optional[bool] = None
    inspection_remarks: Optional[str] = None
    rework_instructions: Optional[str] = None
    inspected_at: Optional[datetime] = None


@router.get("", response_model=list[InspectionOut])
def list_inspections(
    status: Optional[str] = None,
    user: User = Depends(PLANNING_OR_ABOVE),
    db: Session = Depends(get_db),
):
    q = db.query(StandardInspection)
    if status:
        try:
            q = q.filter(StandardInspection.status == InspectionStatus(status))
        except ValueError:
            pass
    return q.order_by(StandardInspection.created_at.desc()).all()


@router.get("/job/{job_id}", response_model=InspectionOut)
def get_inspection(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_ABOVE), db: Session = Depends(get_db)):
    record = db.query(StandardInspection).filter(StandardInspection.job_id == job_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="No inspection record for this job")
    return record


@router.post("/job/{job_id}", response_model=InspectionOut, status_code=201)
def create_inspection(
    job_id: uuid.UUID,
    payload: InspectionCreate,
    user: User = Depends(STANDARD_DEPT),
    db: Session = Depends(get_db),
):
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if db.query(StandardInspection).filter(StandardInspection.job_id == job_id).first():
        raise HTTPException(status_code=409, detail="Inspection already exists for this job")
    record = StandardInspection(
        job_id=job_id,
        inspector_id=user.id,
        quantity_inspected=payload.quantity_inspected,
        inspection_remarks=payload.inspection_remarks,
        packaging_ok=payload.packaging_ok,
        quantity_ok=payload.quantity_ok,
        created_by=user.id,
    )
    db.add(record)
    audit_service.record(db, user=user, action="INSPECTION_CREATED", entity_type="StandardInspection")
    db.commit()
    db.refresh(record)
    return record


@router.put("/{record_id}/decide", response_model=InspectionOut)
async def submit_inspection_decision(
    record_id: uuid.UUID,
    payload: InspectionDecision,
    user: User = Depends(STANDARD_DEPT),
    db: Session = Depends(get_db),
):
    record = db.query(StandardInspection).filter(StandardInspection.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Inspection record not found")

    old_status = record.status.value
    record.status = payload.status
    record.inspected_at = datetime.utcnow()
    record.inspector_id = user.id
    if payload.quantity_inspected is not None:
        record.quantity_inspected = payload.quantity_inspected
    if payload.packaging_ok is not None:
        record.packaging_ok = payload.packaging_ok
    if payload.quantity_ok is not None:
        record.quantity_ok = payload.quantity_ok
    if payload.inspection_remarks:
        record.inspection_remarks = payload.inspection_remarks
    if payload.rework_instructions:
        record.rework_instructions = payload.rework_instructions
    record.updated_by = user.id

    audit_service.record(
        db, user=user, action=f"INSPECTION_{payload.status.value}",
        entity_type="StandardInspection", entity_id=record.id,
        before={"status": old_status}, after={"status": payload.status.value},
    )
    db.commit()
    db.refresh(record)

    if payload.status == InspectionStatus.PASSED:
        job = db.query(ProductionJob).filter(ProductionJob.id == record.job_id).first()
        await manager.broadcast(
            "INSPECTION_PASSED",
            {"job_id": str(record.job_id), "job_number": job.job_number if job else ""},
            visible_to_departments={DepartmentCode.DISPATCH.value, DepartmentCode.PLANNING.value},
        )
    return record


@router.get("/dispatch-readiness/{job_id}")
def check_dispatch_readiness(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_ABOVE), db: Session = Depends(get_db)):
    """Dispatch uses this to verify a job passed standard before dispatching."""
    inspection = db.query(StandardInspection).filter(StandardInspection.job_id == job_id).first()
    if not inspection:
        return {"ready": False, "reason": "No standard inspection record found"}
    if inspection.status != InspectionStatus.PASSED:
        return {"ready": False, "reason": f"Inspection status is {inspection.status.value}, not PASSED"}
    return {"ready": True, "reason": "Standard inspection passed", "inspection_id": str(inspection.id)}
