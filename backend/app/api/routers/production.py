import random
import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments
from app.models.enums import DepartmentCode, JobStatus, DispatchStatus
from app.models.production import ProductionJob, ProductionJobMaterial, DispatchOrder
from app.models.material import Material
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/production", tags=["production"])
dispatch_router = APIRouter(prefix="/api/dispatch", tags=["dispatch"])

PLANNING_ONLY = require_departments(DepartmentCode.PLANNING)
DISPATCH_ONLY = require_departments(DepartmentCode.DISPATCH)


class JobMaterialIn(BaseModel):
    material_id: uuid.UUID
    quantity_required: Decimal


class JobCreate(BaseModel):
    client_name: str
    work_name: str
    pages: Optional[int] = None
    copies: Optional[int] = None
    priority: str = "NORMAL"
    deadline: Optional[datetime] = None
    materials: list[JobMaterialIn] = []


class JobMaterialAvailability(BaseModel):
    material_id: uuid.UUID
    material_name: str
    required: Decimal
    available: Decimal
    status: str  # GREEN / RED


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_number: str
    client_name: str
    work_name: str
    status: str
    priority: str


# ---------------- Production Jobs: PLANNING only (+ manager/sub-admin) ----------------
@router.get("/jobs", response_model=list[JobOut])
def list_jobs(user: User = Depends(PLANNING_ONLY), db: Session = Depends(get_db)):
    return db.query(ProductionJob).order_by(ProductionJob.created_at.desc()).all()


@router.post("/jobs", response_model=JobOut, status_code=201)
async def create_job(payload: JobCreate, user: User = Depends(PLANNING_ONLY), db: Session = Depends(get_db)):
    job_number = "JOB-" + "".join(random.choices(string.digits, k=6))
    job = ProductionJob(job_number=job_number, client_name=payload.client_name, work_name=payload.work_name,
                         pages=payload.pages, copies=payload.copies, priority=payload.priority,
                         deadline=payload.deadline, status=JobStatus.PLANNED, created_by=user.id)
    db.add(job)
    db.flush()
    for m in payload.materials:
        db.add(ProductionJobMaterial(job_id=job.id, material_id=m.material_id, quantity_required=m.quantity_required))
    audit_service.record(db, user=user, action="JOB_CREATED", entity_type="ProductionJob", entity_id=job.id)
    db.commit()
    db.refresh(job)
    await manager.broadcast("JOB_CREATED", {"job_id": str(job.id), "job_number": job.job_number},
                             visible_to_departments={DepartmentCode.PLANNING.value})
    return job


@router.get("/jobs/{job_id}/availability", response_model=list[JobMaterialAvailability])
def job_availability(job_id: uuid.UUID, user: User = Depends(PLANNING_ONLY), db: Session = Depends(get_db)):
    """GREEN/RED material availability check against current stock, per spec section 11."""
    job = db.query(ProductionJob).options(joinedload(ProductionJob.materials)).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    result = []
    for jm in job.materials:
        material = db.query(Material).get(jm.material_id)
        status = "GREEN" if material.current_stock >= jm.quantity_required else "RED"
        result.append(JobMaterialAvailability(
            material_id=material.id, material_name=material.name,
            required=jm.quantity_required, available=material.current_stock, status=status,
        ))
    return result


@router.put("/jobs/{job_id}/status", response_model=JobOut)
async def update_job_status(job_id: uuid.UUID, status: JobStatus, user: User = Depends(PLANNING_ONLY), db: Session = Depends(get_db)):
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = status
    audit_service.record(db, user=user, action="JOB_UPDATED", entity_type="ProductionJob", entity_id=job.id)
    db.commit()
    db.refresh(job)
    await manager.broadcast("JOB_UPDATED", {"job_id": str(job.id), "status": job.status.value},
                             visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.DISPATCH.value})
    return job


# ---------------- Dispatch: DISPATCH only (+ manager/sub-admin) ----------------
class DispatchCreate(BaseModel):
    job_id: Optional[uuid.UUID] = None
    recipient: str
    quantity: int
    vehicle_or_courier: Optional[str] = None
    remarks: Optional[str] = None


class DispatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    dispatch_no: str
    recipient: str
    quantity: int
    status: str


@dispatch_router.get("", response_model=list[DispatchOut])
def list_dispatches(user: User = Depends(DISPATCH_ONLY), db: Session = Depends(get_db)):
    return db.query(DispatchOrder).order_by(DispatchOrder.created_at.desc()).all()


@dispatch_router.post("", response_model=DispatchOut, status_code=201)
async def create_dispatch(payload: DispatchCreate, user: User = Depends(DISPATCH_ONLY), db: Session = Depends(get_db)):
    dispatch_no = "DSP-" + "".join(random.choices(string.digits, k=6))
    d = DispatchOrder(dispatch_no=dispatch_no, job_id=payload.job_id, recipient=payload.recipient,
                       quantity=payload.quantity, vehicle_or_courier=payload.vehicle_or_courier,
                       remarks=payload.remarks, status=DispatchStatus.PENDING, created_by=user.id)
    db.add(d)
    audit_service.record(db, user=user, action="DISPATCH_CREATED", entity_type="DispatchOrder")
    db.commit()
    db.refresh(d)
    await manager.broadcast("DISPATCH_CREATED", {"dispatch_no": d.dispatch_no},
                             visible_to_departments={DepartmentCode.DISPATCH.value})
    return d


@dispatch_router.put("/{dispatch_id}/status", response_model=DispatchOut)
async def update_dispatch_status(dispatch_id: uuid.UUID, status: DispatchStatus, user: User = Depends(DISPATCH_ONLY), db: Session = Depends(get_db)):
    d = db.query(DispatchOrder).filter(DispatchOrder.id == dispatch_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dispatch order not found")
    d.status = status
    if status == DispatchStatus.DISPATCHED:
        d.dispatch_date = datetime.utcnow()
    audit_service.record(db, user=user, action="DISPATCH_UPDATED", entity_type="DispatchOrder", entity_id=d.id)
    db.commit()
    db.refresh(d)
    return d
