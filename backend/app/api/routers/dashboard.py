from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, is_cross_department
from app.models.enums import DepartmentCode, RequestStatus, PurchaseOrderStatus, JobStatus, DispatchStatus
from app.models.material import Material
from app.models.request import MaterialRequest
from app.models.purchase import PurchaseOrder
from app.models.production import ProductionJob, DispatchOrder
from app.models.accounts import Expense, Budget
from app.models.user import User

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dept_code = user.department.code
    data = {"department": dept_code.value}

    if is_cross_department(user):
        total_materials = db.query(func.count(Material.id)).filter(Material.is_active == True).scalar()  # noqa: E712
        low_stock = db.query(func.count(Material.id)).filter(Material.is_active == True, Material.current_stock <= Material.reorder_level).scalar()  # noqa: E712
        out_of_stock = db.query(func.count(Material.id)).filter(Material.is_active == True, Material.current_stock <= 0).scalar()  # noqa: E712
        inventory_value = db.query(func.coalesce(func.sum(Material.current_stock * Material.purchase_price), 0)).scalar()
        pending_requests = db.query(func.count(MaterialRequest.id)).filter(
            MaterialRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.PENDING_APPROVAL])
        ).scalar()
        pending_pos = db.query(func.count(PurchaseOrder.id)).filter(PurchaseOrder.status == PurchaseOrderStatus.ORDERED).scalar()
        monthly_spend = db.query(func.coalesce(func.sum(Expense.amount), 0)).scalar()
        open_jobs = db.query(func.count(ProductionJob.id)).filter(ProductionJob.status.in_([JobStatus.PLANNED, JobStatus.IN_PROGRESS])).scalar()
        pending_dispatch = db.query(func.count(DispatchOrder.id)).filter(DispatchOrder.status.in_([DispatchStatus.PENDING, DispatchStatus.READY])).scalar()
        data.update({
            "total_materials": total_materials,
            "low_stock_count": low_stock,
            "out_of_stock_count": out_of_stock,
            "inventory_value": str(inventory_value),
            "pending_material_requests": pending_requests,
            "pending_purchase_orders": pending_pos,
            "total_recorded_spend": str(monthly_spend),
            "open_production_jobs": open_jobs,
            "pending_dispatch_orders": pending_dispatch,
            "scope": "ALL_DEPARTMENTS",
        })
        return data

    if dept_code == DepartmentCode.STORE:
        data.update({
            "total_materials": db.query(func.count(Material.id)).filter(Material.is_active == True).scalar(),  # noqa: E712
            "low_stock_count": db.query(func.count(Material.id)).filter(Material.is_active == True, Material.current_stock <= Material.reorder_level).scalar(),  # noqa: E712
            "pending_material_requests": db.query(func.count(MaterialRequest.id)).filter(
                MaterialRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.PENDING_APPROVAL, RequestStatus.APPROVED])
            ).scalar(),
            "scope": "STORE",
        })
    elif dept_code == DepartmentCode.PLANNING:
        data.update({
            "my_open_jobs": db.query(func.count(ProductionJob.id)).filter(ProductionJob.status.in_([JobStatus.PLANNED, JobStatus.IN_PROGRESS])).scalar(),
            "my_pending_requests": db.query(func.count(MaterialRequest.id)).filter(
                MaterialRequest.requesting_department_id == user.department_id,
                MaterialRequest.status.in_([RequestStatus.SUBMITTED, RequestStatus.PENDING_APPROVAL]),
            ).scalar(),
            "scope": "PLANNING",
        })
    elif dept_code == DepartmentCode.DISPATCH:
        data.update({
            "pending_dispatch_orders": db.query(func.count(DispatchOrder.id)).filter(DispatchOrder.status.in_([DispatchStatus.PENDING, DispatchStatus.READY])).scalar(),
            "scope": "DISPATCH",
        })
    elif dept_code == DepartmentCode.ACCOUNTS:
        data.update({
            "total_recorded_spend": str(db.query(func.coalesce(func.sum(Expense.amount), 0)).scalar()),
            "budget_lines": db.query(func.count(Budget.id)).scalar(),
            "scope": "ACCOUNTS",
        })
    else:  # EMPLOYEE
        data.update({
            "my_requests": db.query(func.count(MaterialRequest.id)).filter(
                MaterialRequest.requested_by == user.id
            ).scalar(),
            "scope": "SELF_ONLY",
        })
    return data
