"""
Binding/Finishing API — BINDING department tracks finishing operations.
"""
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import require_departments
from app.models.enums import DepartmentCode, FinishingMethod
from app.models.press_workflow import FinishingOperation
from app.models.production import ProductionJob
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/binding", tags=["binding"])

BINDING_DEPT = require_departments(DepartmentCode.BINDING)
PLANNING_OR_ABOVE = require_departments(DepartmentCode.PLANNING, DepartmentCode.BINDING)


class FinishingCreate(BaseModel):
    finishing_method: FinishingMethod = FinishingMethod.NONE
    quantity_received: int = 0
    remarks: Optional[str] = None


class FinishingUpdate(BaseModel):
    quantity_completed: Optional[int] = None
    quantity_pending: Optional[int] = None
    finishing_method: Optional[FinishingMethod] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_complete: Optional[bool] = None
    remarks: Optional[str] = None


class FinishingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    finishing_method: str
    quantity_received: int
    quantity_completed: int
    quantity_pending: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    is_complete: bool
    remarks: Optional[str] = None


@router.get("", response_model=list[FinishingOut])
def list_finishing_operations(
    complete: Optional[bool] = None,
    user: User = Depends(PLANNING_OR_ABOVE),
    db: Session = Depends(get_db),
):
    q = db.query(FinishingOperation)
    if complete is not None:
        q = q.filter(FinishingOperation.is_complete == complete)
    return q.order_by(FinishingOperation.created_at.desc()).all()


@router.get("/job/{job_id}", response_model=FinishingOut)
def get_finishing_for_job(job_id: uuid.UUID, user: User = Depends(PLANNING_OR_ABOVE), db: Session = Depends(get_db)):
    record = db.query(FinishingOperation).filter(FinishingOperation.job_id == job_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="No finishing record for this job")
    return record


@router.post("/job/{job_id}", response_model=FinishingOut, status_code=201)
def create_finishing_operation(
    job_id: uuid.UUID,
    payload: FinishingCreate,
    user: User = Depends(BINDING_DEPT),
    db: Session = Depends(get_db),
):
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    existing = db.query(FinishingOperation).filter(FinishingOperation.job_id == job_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Finishing operation already exists for this job; use PUT to update")
    op = FinishingOperation(
        job_id=job_id,
        operator_id=user.id,
        finishing_method=payload.finishing_method,
        quantity_received=payload.quantity_received,
        quantity_pending=payload.quantity_received,
        started_at=datetime.utcnow(),
        created_by=user.id,
    )
    db.add(op)
    audit_service.record(db, user=user, action="FINISHING_STARTED", entity_type="FinishingOperation", entity_id=op.id)
    db.commit()
    db.refresh(op)
    return op


@router.put("/{op_id}", response_model=FinishingOut)
async def update_finishing_operation(
    op_id: uuid.UUID,
    payload: FinishingUpdate,
    user: User = Depends(BINDING_DEPT),
    db: Session = Depends(get_db),
):
    op = db.query(FinishingOperation).filter(FinishingOperation.id == op_id).first()
    if not op:
        raise HTTPException(status_code=404, detail="Finishing operation not found")

    data = payload.model_dump(exclude_unset=True)
    if "quantity_completed" in data:
        completed = data["quantity_completed"]
        if completed > op.quantity_received:
            raise HTTPException(status_code=400, detail="Completed quantity cannot exceed received quantity")
        op.quantity_pending = op.quantity_received - completed

    for field, value in data.items():
        setattr(op, field, value)

    if op.quantity_completed >= op.quantity_received and op.quantity_received > 0:
        op.is_complete = True
        if not op.completed_at:
            op.completed_at = datetime.utcnow()

    op.updated_by = user.id
    audit_service.record(db, user=user, action="FINISHING_UPDATED", entity_type="FinishingOperation", entity_id=op.id)
    db.commit()
    db.refresh(op)

    if op.is_complete:
        job = db.query(ProductionJob).filter(ProductionJob.id == op.job_id).first()
        await manager.broadcast(
            "BINDING_COMPLETE",
            {"job_id": str(op.job_id), "job_number": job.job_number if job else ""},
            visible_to_departments={DepartmentCode.STANDARD.value, DepartmentCode.DISPATCH.value, DepartmentCode.PLANNING.value},
        )
    return op
