from sqlalchemy import Column, String, Numeric, ForeignKey, Boolean
from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, GUID


class CostingRateMaster(Base, IDMixin, TimestampMixin, AuditMixin):
    """The editable rate master driving the 3-formula Ready Reckoner. Only
    one row is active at a time; every change is versioned + audited (see
    audit_logs) rather than silently overwritten. MANAGER/SUB_ADMIN edit;
    ACCOUNTS + PLANNING may read (they need it for estimates/budgets)."""
    __tablename__ = "costing_rate_master"

    label = Column(String(120), nullable=False, default="Default Rate Master")
    is_active = Column(Boolean, default=True, nullable=False)

    dtp_rate = Column(Numeric(10, 2), nullable=False)
    proof_rate = Column(Numeric(10, 2), nullable=False)
    ctp_rate = Column(Numeric(10, 2), nullable=False)
    offset_printing_first_rate = Column(Numeric(10, 2), nullable=False)
    binding_rate = Column(Numeric(10, 2), nullable=False)
    warehouse_loading_pct = Column(Numeric(5, 2), nullable=False, default=15)
    dispatch_pct = Column(Numeric(5, 2), nullable=False, default=3)
    book_depot_pct = Column(Numeric(5, 2), nullable=False, default=0)


class CostEstimate(Base, IDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "cost_estimates"

    job_id = Column(GUID(), ForeignKey("production_jobs.id"), nullable=True)
    rate_master_id = Column(GUID(), ForeignKey("costing_rate_master.id"), nullable=False)

    pages = Column(Numeric(10, 0), nullable=False, default=0)
    copies = Column(Numeric(10, 0), nullable=False, default=0)
    plates = Column(Numeric(10, 0), nullable=False, default=0)
    impressions_thousands = Column(Numeric(12, 3), nullable=False, default=0)
    paper_cost = Column(Numeric(14, 2), nullable=False, default=0)
    printing_rate_used = Column(Numeric(10, 2), nullable=False)
    binding_rate_used = Column(Numeric(10, 2), nullable=False)

    fixed_prepress_cost = Column(Numeric(14, 2), nullable=False)
    variable_cost = Column(Numeric(14, 2), nullable=False)
    final_landed_billing_cost = Column(Numeric(14, 2), nullable=False)
    per_copy_rate = Column(Numeric(14, 4), nullable=False)
