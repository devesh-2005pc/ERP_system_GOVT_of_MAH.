"""
Plate Making API — PLATE_MAKING department tracks CTP plate preparation.
Planning creates the plate record; Plate Making dept updates status.
"""
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments
from app.models.enums import DepartmentCode, PlateStatus
from app.models.press_workflow import PlateMakingRecord
from app.models.production import ProductionJob
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/plate-making", tags=["plate-making"])

PLATE_MAKING_DEPT = require_departments(DepartmentCode.PLATE_MAKING)
PLANNING_OR_ABOVE = require_departments(DepartmentCode.PLANNING, DepartmentCode.PLATE_MAKING)


class PlateUpdateIn(BaseModel):
    plate_count: Optional[int] = None
    plate_size: Optional[str] = None
    status: Optional[PlateStatus] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    remarks: Optional[str] = None


class PlateWaiverIn(BaseModel):
    reason: str


class PlateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    plate_count: Optional[int] = None
    plate_size: Optional[str] = None
    status: str
    requirement_waived: bool
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    remarks: Optional[str] = None


@router.get("", response_model=list[PlateOut])
def list_plate_records(
    status: Optional[str] = None,
    user: User = Depends(PLANNING_OR_ABOVE),
    db: Session = Depends(get_db),
):
    q = db.query(PlateMakingRecord)
    if status:
        try:
            q = q.filter(PlateMakingRecord.status == PlateStatus(status))
        except ValueError:
            pass
    return q.order_by(PlateMakingRecord.created_at.desc()).all()


@router.get("/job/{job_id}", response_model=PlateOut)
def get_plate_record(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_ABOVE), db: Session = Depends(get_db)):
    record = db.query(PlateMakingRecord).filter(PlateMakingRecord.job_id == job_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="No plate making record for this job")
    return record


@router.put("/{record_id}", response_model=PlateOut)
async def update_plate_record(
    record_id: uuid.UUID,
    payload: PlateUpdateIn,
    user: User = Depends(PLATE_MAKING_DEPT),
    db: Session = Depends(get_db),
):
    record = db.query(PlateMakingRecord).filter(PlateMakingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Plate making record not found")
    old_status = record.status.value
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    record.updated_by = user.id
    audit_service.record(
        db, user=user, action="PLATE_STATUS_UPDATED", entity_type="PlateMakingRecord", entity_id=record.id,
        before={"status": old_status}, after={"status": payload.status.value if payload.status else old_status},
    )
    db.commit()
    db.refresh(record)
    if record.status == PlateStatus.COMPLETED:
        job = db.query(ProductionJob).filter(ProductionJob.id == record.job_id).first()
        await manager.broadcast(
            "PLATES_READY",
            {"job_id": str(record.job_id), "job_number": job.job_number if job else ""},
            visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.TRADITIONAL_PRINTING.value},
        )
    return record


@router.post("/{record_id}/waive", response_model=PlateOut)
def waive_plate_requirement(
    record_id: uuid.UUID,
    payload: PlateWaiverIn,
    user: User = Depends(require_departments(DepartmentCode.PLANNING)),
    db: Session = Depends(get_db),
):
    """Planning can waive plate requirement for jobs that do not need plates."""
    record = db.query(PlateMakingRecord).filter(PlateMakingRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Plate making record not found")
    record.requirement_waived = True
    record.waived_by = user.id
    record.waiver_reason = payload.reason
    record.status = PlateStatus.NOT_REQUIRED
    record.updated_by = user.id
    audit_service.record(db, user=user, action="PLATE_REQUIREMENT_WAIVED", entity_type="PlateMakingRecord",
                          entity_id=record.id, detail=payload.reason)
    db.commit()
    db.refresh(record)
    return record
