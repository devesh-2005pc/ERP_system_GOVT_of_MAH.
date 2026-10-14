import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_manager_or_subadmin, require_departments
from app.models.enums import DepartmentCode
from app.models.costing import CostingRateMaster, CostEstimate
from app.models.user import User
from app.services import audit as audit_service

router = APIRouter(prefix="/api/costing", tags=["costing"])

# Rates are readable by PLANNING (needs it for estimates) + ACCOUNTS (budgets)
# + MANAGER/SUB_ADMIN; editable only by MANAGER/SUB_ADMIN.
RATE_READERS = require_departments(DepartmentCode.PLANNING, DepartmentCode.ACCOUNTS)


class RateMasterIn(BaseModel):
    label: str = "Default Rate Master"
    dtp_rate: Decimal
    proof_rate: Decimal
    ctp_rate: Decimal
    offset_printing_first_rate: Decimal
    binding_rate: Decimal
    warehouse_loading_pct: Decimal = Decimal("15")
    dispatch_pct: Decimal = Decimal("3")
    book_depot_pct: Decimal = Decimal("0")


class RateMasterOut(RateMasterIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    is_active: bool


class EstimateInput(BaseModel):
    job_id: Optional[uuid.UUID] = None
    pages: int = 0
    copies: int = 0
    plates: int = 0
    impressions_thousands: Optional[Decimal] = None
    paper_cost: Decimal = Decimal("0")
    printing_rate: Optional[Decimal] = None
    binding_rate: Optional[Decimal] = None


class EstimateOut(BaseModel):
    breakdown: dict
    final_landed_billing_cost: Decimal
    per_copy_rate: Decimal


def compute_estimate(payload: EstimateInput, rate_master: CostingRateMaster) -> dict:
    """The exact 3-formula Ready Reckoner from the original project, ported
    to Python/Decimal for correctness (the Node version used floats)."""
    pages = Decimal(payload.pages or 0)
    copies = Decimal(payload.copies or 0)
    plates = Decimal(payload.plates or 0)
    impressions_thousands = payload.impressions_thousands
    if impressions_thousands is None:
        impressions_thousands = (plates * copies) / Decimal(1000) if plates and copies else Decimal(0)
    paper_cost = payload.paper_cost or Decimal(0)
    printing_rate = payload.printing_rate if payload.printing_rate is not None else rate_master.offset_printing_first_rate
    binding_rate = payload.binding_rate if payload.binding_rate is not None else rate_master.binding_rate

    dtp_cost = pages * rate_master.dtp_rate
    proof_cost = pages * rate_master.proof_rate
    plate_cost = plates * rate_master.ctp_rate
    F = dtp_cost + proof_cost + plate_cost

    printing_cost = impressions_thousands * printing_rate
    binding_cost = copies * binding_rate
    warehouse_loading = paper_cost * (rate_master.warehouse_loading_pct / Decimal(100))
    paper_total = paper_cost + warehouse_loading
    V = printing_cost + binding_cost + paper_total

    net_production_cost = F + V
    dispatch_charge = net_production_cost * (rate_master.dispatch_pct / Decimal(100))
    book_depot_charge = net_production_cost * (rate_master.book_depot_pct / Decimal(100))
    B = net_production_cost + dispatch_charge + book_depot_charge

    per_copy_rate = (B / copies) if copies > 0 else Decimal(0)

    return {
        "breakdown": {
            "dtp_cost": str(dtp_cost), "proof_cost": str(proof_cost), "plate_cost": str(plate_cost),
            "fixed_prepress_cost": str(F), "printing_cost": str(printing_cost), "binding_cost": str(binding_cost),
            "warehouse_loading": str(warehouse_loading), "paper_total": str(paper_total), "variable_cost": str(V),
            "net_production_cost": str(net_production_cost), "dispatch_charge": str(dispatch_charge),
            "book_depot_charge": str(book_depot_charge),
        },
        "final_landed_billing_cost": B,
        "per_copy_rate": per_copy_rate,
        "printing_rate_used": printing_rate,
        "binding_rate_used": binding_rate,
        "pages": pages, "copies": copies, "plates": plates,
        "impressions_thousands": impressions_thousands, "paper_cost": paper_cost,
        "fixed_prepress_cost": F, "variable_cost": V,
    }


def _get_active_rate_master(db: Session) -> CostingRateMaster:
    rm = db.query(CostingRateMaster).filter(CostingRateMaster.is_active == True).first()  # noqa: E712
    if not rm:
        raise HTTPException(status_code=400, detail="No active costing rate master configured")
    return rm


@router.get("/rates", response_model=RateMasterOut)
def get_rates(user: User = Depends(RATE_READERS), db: Session = Depends(get_db)):
    return _get_active_rate_master(db)


@router.put("/rates", response_model=RateMasterOut)
def set_rates(payload: RateMasterIn, user: User = Depends(require_manager_or_subadmin), db: Session = Depends(get_db)):
    """Every rate change is audited (before/after), per spec section 18."""
    old = db.query(CostingRateMaster).filter(CostingRateMaster.is_active == True).first()  # noqa: E712
    before = None
    if old:
        before = {c.name: str(getattr(old, c.name)) for c in old.__table__.columns if c.name not in ("id", "created_at", "updated_at")}
        old.is_active = False
    new = CostingRateMaster(**payload.model_dump(), is_active=True, created_by=user.id)
    db.add(new)
    audit_service.record(db, user=user, action="COSTING_RATES_CHANGED", entity_type="CostingRateMaster",
                          before=before, after=payload.model_dump(mode="json"))
    db.commit()
    db.refresh(new)
    return new


@router.post("/estimate", response_model=EstimateOut)
def preview_estimate(payload: EstimateInput, user: User = Depends(RATE_READERS), db: Session = Depends(get_db)):
    rm = _get_active_rate_master(db)
    result = compute_estimate(payload, rm)
    return EstimateOut(breakdown=result["breakdown"], final_landed_billing_cost=result["final_landed_billing_cost"],
                        per_copy_rate=result["per_copy_rate"])


@router.post("/estimate/save", response_model=EstimateOut, status_code=201)
def save_estimate(payload: EstimateInput, user: User = Depends(RATE_READERS), db: Session = Depends(get_db)):
    rm = _get_active_rate_master(db)
    result = compute_estimate(payload, rm)
    est = CostEstimate(
        job_id=payload.job_id, rate_master_id=rm.id, pages=result["pages"], copies=result["copies"],
        plates=result["plates"], impressions_thousands=result["impressions_thousands"], paper_cost=result["paper_cost"],
        printing_rate_used=result["printing_rate_used"], binding_rate_used=result["binding_rate_used"],
        fixed_prepress_cost=result["fixed_prepress_cost"], variable_cost=result["variable_cost"],
        final_landed_billing_cost=result["final_landed_billing_cost"], per_copy_rate=result["per_copy_rate"],
        created_by=user.id,
    )
    db.add(est)
    audit_service.record(db, user=user, action="COST_ESTIMATE_SAVED", entity_type="CostEstimate")
    db.commit()
    return EstimateOut(breakdown=result["breakdown"], final_landed_billing_cost=result["final_landed_billing_cost"],
                        per_copy_rate=result["per_copy_rate"])
