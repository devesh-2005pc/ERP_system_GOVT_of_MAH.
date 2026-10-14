import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments, is_cross_department
from app.models.enums import DepartmentCode, TxnType
from app.models.material import Material, InventoryTransaction
from app.models.accounts import Expense
from app.models.user import User

router = APIRouter(prefix="/api/reports", tags=["reports"])
STORE_OR_ABOVE = require_departments(DepartmentCode.STORE)
ACCOUNTS_OR_ABOVE = require_departments(DepartmentCode.ACCOUNTS)


def _export(rows: list[dict], fmt: str, filename: str):
    if not rows:
        rows = []
    if fmt == "csv":
        buf = io.StringIO()
        if rows:
            writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                                  headers={"Content-Disposition": f"attachment; filename={filename}.csv"})
    if fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        if rows:
            ws.append(list(rows[0].keys()))
            for r in rows:
                ws.append(list(r.values()))
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return StreamingResponse(out, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                  headers={"Content-Disposition": f"attachment; filename={filename}.xlsx"})
    return rows


@router.get("/inventory")
def inventory_report(fmt: str = Query("json", pattern="^(json|csv|xlsx)$"), user: User = Depends(STORE_OR_ABOVE), db: Session = Depends(get_db)):
    """Current inventory + valuation, derived entirely from live DB rows."""
    materials = db.query(Material).filter(Material.is_active == True).order_by(Material.name).all()  # noqa: E712
    rows = [{
        "sku": m.sku, "name": m.name, "unit": m.unit, "current_stock": str(m.current_stock),
        "minimum_stock": str(m.minimum_stock), "reorder_level": str(m.reorder_level),
        "purchase_price": str(m.purchase_price or 0),
        "valuation": str((m.current_stock or 0) * (m.purchase_price or 0)),
        "status": "LOW_STOCK" if m.current_stock <= m.reorder_level else "OK",
    } for m in materials]
    return _export(rows, fmt, "inventory_report")


@router.get("/low-stock")
def low_stock_report(user: User = Depends(STORE_OR_ABOVE), db: Session = Depends(get_db)):
    materials = db.query(Material).filter(Material.is_active == True, Material.current_stock <= Material.reorder_level).all()  # noqa: E712
    return [{"sku": m.sku, "name": m.name, "current_stock": str(m.current_stock), "reorder_level": str(m.reorder_level)} for m in materials]


@router.get("/consumption")
def consumption_report(
    material_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    fmt: str = Query("json", pattern="^(json|csv|xlsx)$"),
    user: User = Depends(STORE_OR_ABOVE),
    db: Session = Depends(get_db),
):
    """Material consumption (ISSUE transactions), grouped by material - real
    ledger data, not estimates."""
    q = db.query(
        Material.sku, Material.name,
        func.sum(-InventoryTransaction.quantity).label("total_issued"),
    ).join(InventoryTransaction, InventoryTransaction.material_id == Material.id).filter(
        InventoryTransaction.txn_type == TxnType.ISSUE
    )
    if material_id:
        q = q.filter(Material.id == material_id)
    if start_date:
        q = q.filter(InventoryTransaction.created_at >= start_date)
    if end_date:
        q = q.filter(InventoryTransaction.created_at <= end_date)
    q = q.group_by(Material.id).order_by(func.sum(-InventoryTransaction.quantity).desc())
    rows = [{"sku": sku, "name": name, "total_issued": str(total)} for sku, name, total in q.all()]
    return _export(rows, fmt, "consumption_report")


@router.get("/expenses")
def expenses_report(
    department_id: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    fmt: str = Query("json", pattern="^(json|csv|xlsx)$"),
    user: User = Depends(ACCOUNTS_OR_ABOVE),
    db: Session = Depends(get_db),
):
    q = db.query(Expense)
    if department_id:
        q = q.filter(Expense.department_id == department_id)
    if start_date:
        q = q.filter(Expense.expense_date >= start_date)
    if end_date:
        q = q.filter(Expense.expense_date <= end_date)
    rows = [{
        "date": e.expense_date.isoformat(), "category": e.category.value, "amount": str(e.amount),
        "description": e.description or "",
    } for e in q.order_by(Expense.expense_date.desc()).all()]
    return _export(rows, fmt, "expenses_report")


@router.get("/department-spending")
def department_spending(user: User = Depends(ACCOUNTS_OR_ABOVE), db: Session = Depends(get_db)):
    rows = db.query(Expense.department_id, func.sum(Expense.amount)).group_by(Expense.department_id).all()
    return [{"department_id": str(dept_id) if dept_id else None, "total_spent": str(total)} for dept_id, total in rows]
