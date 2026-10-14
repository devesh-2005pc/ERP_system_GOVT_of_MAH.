from sqlalchemy import Column, String, Numeric, ForeignKey, Enum as SAEnum, DateTime, Integer
from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, GUID
from app.models.enums import ExpenseCategory


class Budget(Base, IDMixin, TimestampMixin, AuditMixin):
    """ACCOUNTS department only (+ MANAGER/SUB_ADMIN)."""
    __tablename__ = "budgets"

    department_id = Column(GUID(), ForeignKey("departments.id"), nullable=True)
    fiscal_year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=True)  # null = annual budget line
    category = Column(SAEnum(ExpenseCategory), nullable=False, default=ExpenseCategory.OTHER)
    allocated_amount = Column(Numeric(14, 2), nullable=False)


class Expense(Base, IDMixin, TimestampMixin, AuditMixin):
    """ACCOUNTS department only (+ MANAGER/SUB_ADMIN)."""
    __tablename__ = "expenses"

    department_id = Column(GUID(), ForeignKey("departments.id"), nullable=True)
    category = Column(SAEnum(ExpenseCategory), nullable=False, default=ExpenseCategory.OTHER)
    amount = Column(Numeric(14, 2), nullable=False)
    description = Column(String(500), nullable=True)
    supplier_id = Column(GUID(), ForeignKey("suppliers.id"), nullable=True)
    purchase_order_id = Column(GUID(), ForeignKey("purchase_orders.id"), nullable=True)
    expense_date = Column(DateTime, nullable=False)
