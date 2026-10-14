"""
Machines API — CRUD + status management.
Readable by PLANNING (assignment workflow).
Created/edited by MANAGER/SUB_ADMIN.
Status updates by PLANNING (assign/unassign) and MECHANIC (maintenance).
"""
import uuid
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments, require_manager_or_subadmin
from app.models.enums import DepartmentCode, MachineStatus, PrintingMethod
from app.models.press_workflow import Machine, MachineMaintenance
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/machines", tags=["machines"])

PLANNING_OR_ABOVE = require_departments(DepartmentCode.PLANNING)
MECHANIC_OR_ABOVE = require_departments(DepartmentCode.MECHANIC)


class MachineCreate(BaseModel):
    machine_code: str
    name: str
    machine_type: Optional[str] = None
    printing_method: Optional[PrintingMethod] = None
    department_code: Optional[DepartmentCode] = None
    location: Optional[str] = None
    max_paper_size: Optional[str] = None
    min_paper_size: Optional[str] = None
    supported_gsm_range: Optional[str] = None
    max_impressions_per_hour: Optional[int] = None
    is_color: bool = False
    remarks: Optional[str] = None


class MachineUpdate(BaseModel):
    name: Optional[str] = None
    machine_type: Optional[str] = None
    printing_method: Optional[PrintingMethod] = None
    department_code: Optional[DepartmentCode] = None
    location: Optional[str] = None
    max_paper_size: Optional[str] = None
    min_paper_size: Optional[str] = None
    supported_gsm_range: Optional[str] = None
    max_impressions_per_hour: Optional[int] = None
    is_color: Optional[bool] = None
    remarks: Optional[str] = None
    is_active: Optional[bool] = None


class MachineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    machine_code: str
    name: str
    machine_type: Optional[str] = None
    printing_method: Optional[str] = None
    department_code: Optional[str] = None
    location: Optional[str] = None
    max_paper_size: Optional[str] = None
    supported_gsm_range: Optional[str] = None
    max_impressions_per_hour: Optional[int] = None
    is_color: bool
    status: str
    is_active: bool
    remarks: Optional[str] = None


class MaintenanceCreate(BaseModel):
    issue_description: str
    assigned_mechanic_id: Optional[uuid.UUID] = None


class MaintenanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    machine_id: uuid.UUID
    issue_description: str
    status: str
    reported_at: datetime
    resolved_at: Optional[datetime] = None
    repair_remarks: Optional[str] = None


@router.get("", response_model=list[MachineOut])
def list_machines(
    status: Optional[str] = None,
    active_only: bool = True,
    user: User = Depends(PLANNING_OR_ABOVE),
    db: Session = Depends(get_db),
):
    q = db.query(Machine)
    if active_only:
        q = q.filter(Machine.is_active == True)  # noqa: E712
    if status:
        try:
            q = q.filter(Machine.status == MachineStatus(status))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    return q.order_by(Machine.name).all()


@router.get("/available", response_model=list[MachineOut])
def list_available_machines(
    printing_method: Optional[str] = None,
    user: User = Depends(PLANNING_OR_ABOVE),
    db: Session = Depends(get_db),
):
    """Available machines only — for Planning to select when assigning a job."""
    q = db.query(Machine).filter(
        Machine.is_active == True,  # noqa: E712
        Machine.status == MachineStatus.AVAILABLE,
    )
    if printing_method:
        try:
            q = q.filter(Machine.printing_method == PrintingMethod(printing_method))
        except ValueError:
            pass
    return q.order_by(Machine.name).all()


@router.get("/{machine_id}", response_model=MachineOut)
def get_machine(machine_id: uuid.UUID, user: User = Depends(PLANNING_OR_ABOVE), db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    return m


@router.post("", response_model=MachineOut, status_code=201)
def create_machine(payload: MachineCreate, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    if db.query(Machine).filter(Machine.machine_code == payload.machine_code).first():
        raise HTTPException(status_code=409, detail="Machine code already exists")
    m = Machine(**payload.model_dump(), created_by=user.id)
    db.add(m)
    audit_service.record(db, user=user, action="MACHINE_CREATED", entity_type="Machine", detail=payload.name)
    db.commit()
    db.refresh(m)
    return m


@router.put("/{machine_id}", response_model=MachineOut)
def update_machine(machine_id: uuid.UUID, payload: MachineUpdate, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(m, field, value)
    m.updated_by = user.id
    audit_service.record(db, user=user, action="MACHINE_UPDATED", entity_type="Machine", entity_id=m.id)
    db.commit()
    db.refresh(m)
    return m


@router.put("/{machine_id}/status", response_model=MachineOut)
async def update_machine_status(
    machine_id: uuid.UUID,
    status: MachineStatus,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Planning or Mechanic or Manager can update machine status."""
    allowed_depts = {DepartmentCode.PLANNING, DepartmentCode.MECHANIC, DepartmentCode.MANAGER, DepartmentCode.SUB_ADMIN}
    if user.department.code not in allowed_depts:
        raise HTTPException(status_code=403, detail="Not authorized to update machine status")
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    old_status = m.status
    m.status = status
    m.updated_by = user.id
    audit_service.record(
        db, user=user, action="MACHINE_STATUS_CHANGED", entity_type="Machine", entity_id=m.id,
        before={"status": old_status.value}, after={"status": status.value},
    )
    db.commit()
    db.refresh(m)
    await manager.broadcast(
        "MACHINE_STATUS_CHANGED",
        {"machine_id": str(m.id), "machine_code": m.machine_code, "name": m.name, "status": m.status.value},
        visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.MECHANIC.value},
    )
    return m


@router.get("/{machine_id}/maintenance", response_model=list[MaintenanceOut])
def list_maintenance(machine_id: uuid.UUID, user: User = Depends(MECHANIC_OR_ABOVE), db: Session = Depends(get_db)):
    return db.query(MachineMaintenance).filter(MachineMaintenance.machine_id == machine_id).order_by(MachineMaintenance.reported_at.desc()).all()


@router.post("/{machine_id}/maintenance", response_model=MaintenanceOut, status_code=201)
async def report_maintenance(
    machine_id: uuid.UUID,
    payload: MaintenanceCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Any authenticated user can report a breakdown; Mechanic assigns and resolves."""
    m = db.query(Machine).filter(Machine.id == machine_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Machine not found")
    record = MachineMaintenance(
        machine_id=machine_id,
        reported_by=user.id,
        assigned_mechanic_id=payload.assigned_mechanic_id,
        issue_description=payload.issue_description,
        created_by=user.id,
    )
    db.add(record)
    # Automatically mark machine unavailable
    if m.status == MachineStatus.AVAILABLE:
        m.status = MachineStatus.UNDER_MAINTENANCE
    audit_service.record(db, user=user, action="MAINTENANCE_REPORTED", entity_type="Machine", entity_id=machine_id)
    db.commit()
    db.refresh(record)
    await manager.broadcast(
        "MACHINE_MAINTENANCE",
        {"machine_id": str(machine_id), "machine_name": m.name, "status": "REPORTED"},
        visible_to_departments={DepartmentCode.PLANNING.value, DepartmentCode.MECHANIC.value},
    )
    return record
