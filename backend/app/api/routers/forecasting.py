import uuid
import statistics
from collections import OrderedDict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import require_departments
from app.models.enums import DepartmentCode, TxnType
from app.models.material import Material, InventoryTransaction
from app.models.user import User

router = APIRouter(prefix="/api/forecast", tags=["forecasting"])
FORECAST_READERS = require_departments(DepartmentCode.STORE, DepartmentCode.PLANNING)

MIN_MONTHS_FOR_FORECAST = 3
DEFAULT_LEAD_TIME_DAYS = 14


@router.get("/materials/{material_id}")
def forecast_material(
    material_id: uuid.UUID,
    lead_time_days: int = Query(DEFAULT_LEAD_TIME_DAYS, ge=1, le=180),
    lookback_months: int = Query(6, ge=1, le=24),
    user: User = Depends(FORECAST_READERS),
    db: Session = Depends(get_db),
):
    """
    Interpretable moving-average forecast, honestly labeled — NOT a claim of
    'AI prediction'. Uses real historical ISSUE transactions only. If there
    isn't enough history, says so plainly instead of guessing (spec section 17).
    """
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    cutoff = datetime.utcnow() - timedelta(days=30 * lookback_months)
    txns = (
        db.query(InventoryTransaction)
        .filter(
            InventoryTransaction.material_id == material_id,
            InventoryTransaction.txn_type == TxnType.ISSUE,
            InventoryTransaction.created_at >= cutoff,
        )
        .order_by(InventoryTransaction.created_at)
        .all()
    )

    monthly = OrderedDict()
    for t in txns:
        key = t.created_at.strftime("%Y-%m")
        monthly[key] = monthly.get(key, 0) + float(-t.quantity)  # ISSUE quantity is stored negative

    months_with_data = len(monthly)
    if months_with_data < MIN_MONTHS_FOR_FORECAST:
        return {
            "material_id": str(material_id),
            "material_name": material.name,
            "current_stock": str(material.current_stock),
            "months_of_data_available": months_with_data,
            "forecast_available": False,
            "message": "Insufficient historical data for reliable forecast.",
        }

    values = list(monthly.values())
    predicted_monthly_demand = statistics.mean(values)
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    avg_daily_demand = predicted_monthly_demand / 30.0

    # Safety stock: cover demand variability during the lead time window
    # (simple, interpretable — a fixed z=1.0 approximation, not a black box).
    safety_stock = stdev * (lead_time_days / 30.0)
    reorder_point = avg_daily_demand * lead_time_days + safety_stock

    current_stock = float(material.current_stock)
    days_of_cover = (current_stock / avg_daily_demand) if avg_daily_demand > 0 else None
    expected_shortage_date = (
        (datetime.utcnow() + timedelta(days=days_of_cover)).date().isoformat()
        if days_of_cover is not None else None
    )

    suggested_purchase_qty = max(0.0, predicted_monthly_demand + safety_stock - current_stock)

    # Confidence: more months + lower relative variability = higher confidence.
    coefficient_of_variation = (stdev / predicted_monthly_demand) if predicted_monthly_demand else 1
    if months_with_data >= 6 and coefficient_of_variation < 0.25:
        confidence = "HIGH"
    elif months_with_data >= 4 and coefficient_of_variation < 0.5:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return {
        "material_id": str(material_id),
        "material_name": material.name,
        "current_stock": str(material.current_stock),
        "months_of_data_available": months_with_data,
        "monthly_consumption_history": monthly,
        "forecast_available": True,
        "method": "Moving average of monthly issued quantity, with variability-based safety stock",
        "predicted_monthly_demand": round(predicted_monthly_demand, 2),
        "safety_stock": round(safety_stock, 2),
        "reorder_point": round(reorder_point, 2),
        "expected_shortage_date": expected_shortage_date,
        "suggested_purchase_quantity": round(suggested_purchase_qty, 2),
        "confidence": confidence,
        "reorder_now": current_stock <= reorder_point,
    }
