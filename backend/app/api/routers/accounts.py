import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments
from app.models.enums import DepartmentCode, ExpenseCategory
from app.models.accounts import Budget, Expense
from app.models.user import User
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
ACCOUNTS_ONLY = require_departments(DepartmentCode.ACCOUNTS)


class BudgetIn(BaseModel):
    department_id: Optional[uuid.UUID] = None
    fiscal_year: int
    month: Optional[int] = None
    category: ExpenseCategory = ExpenseCategory.OTHER
    allocated_amount: Decimal


class BudgetOut(BudgetIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class ExpenseIn(BaseModel):
    department_id: Optional[uuid.UUID] = None
    category: ExpenseCategory = ExpenseCategory.OTHER
    amount: Decimal
    description: Optional[str] = None
    supplier_id: Optional[uuid.UUID] = None
    purchase_order_id: Optional[uuid.UUID] = None
    expense_date: datetime


class ExpenseOut(ExpenseIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(user: User = Depends(ACCOUNTS_ONLY), db: Session = Depends(get_db)):
    return db.query(Budget).all()


@router.post("/budgets", response_model=BudgetOut, status_code=201)
def create_budget(payload: BudgetIn, user: User = Depends(ACCOUNTS_ONLY), db: Session = Depends(get_db)):
    b = Budget(**payload.model_dump(), created_by=user.id)
    db.add(b)
    audit_service.record(db, user=user, action="BUDGET_CREATED", entity_type="Budget")
    db.commit()
    db.refresh(b)
    return b


@router.get("/expenses", response_model=list[ExpenseOut])
def list_expenses(user: User = Depends(ACCOUNTS_ONLY), db: Session = Depends(get_db)):
    return db.query(Expense).order_by(Expense.expense_date.desc()).all()


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
async def create_expense(payload: ExpenseIn, user: User = Depends(ACCOUNTS_ONLY), db: Session = Depends(get_db)):
    expense = Expense(**payload.model_dump(), created_by=user.id)
    db.add(expense)
    audit_service.record(db, user=user, action="EXPENSE_CREATED", entity_type="Expense")
    db.commit()
    db.refresh(expense)

    # Budget alert check
    if expense.department_id:
        year = expense.expense_date.year
        month = expense.expense_date.month
        budget = db.query(Budget).filter(
            Budget.department_id == expense.department_id,
            Budget.fiscal_year == year,
            (Budget.month == month) | (Budget.month.is_(None)),
        ).first()
        if budget:
            total_spent = db.query(func.coalesce(func.sum(Expense.amount), 0)).filter(
                Expense.department_id == expense.department_id,
            ).scalar()
            pct = float(total_spent) / float(budget.allocated_amount) * 100 if budget.allocated_amount else 0
            if pct >= 80:
                await manager.broadcast(
                    "BUDGET_ALERT",
                    {"department_id": str(expense.department_id), "utilization_pct": round(pct, 1)},
                    visible_to_departments={DepartmentCode.ACCOUNTS.value},
                )
    return expense
