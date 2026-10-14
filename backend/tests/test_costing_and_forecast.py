from decimal import Decimal

from tests.conftest import login, auth_headers
from app.api.routers.costing import compute_estimate, EstimateInput


class FakeRateMaster:
    dtp_rate = Decimal("1.50")
    proof_rate = Decimal("0.75")
    ctp_rate = Decimal("120.00")
    offset_printing_first_rate = Decimal("450.00")
    binding_rate = Decimal("3.20")
    warehouse_loading_pct = Decimal("15")
    dispatch_pct = Decimal("3")
    book_depot_pct = Decimal("1")


def test_costing_formula_produces_positive_billing_cost():
    payload = EstimateInput(pages=100, copies=1000, plates=8, paper_cost=Decimal("5000"))
    result = compute_estimate(payload, FakeRateMaster())
    assert result["final_landed_billing_cost"] > 0
    assert result["per_copy_rate"] > 0


def test_costing_zero_copies_does_not_divide_by_zero():
    payload = EstimateInput(pages=10, copies=0, plates=1, paper_cost=Decimal("100"))
    result = compute_estimate(payload, FakeRateMaster())
    assert result["per_copy_rate"] == Decimal(0)


def test_costing_endpoint_rbac(client, seeded):
    dispatch_token = login(client, "DSP001", "Dispatch@123")
    r = client.get("/api/costing/rates", headers=auth_headers(dispatch_token))
    assert r.status_code == 403  # Dispatch has no need for costing rates

    planning_token = login(client, "PLN001", "Planning@123")
    r = client.get("/api/costing/rates", headers=auth_headers(planning_token))
    assert r.status_code == 200


def test_only_manager_or_subadmin_can_change_rates(client, seeded):
    planning_token = login(client, "PLN001", "Planning@123")
    r = client.put("/api/costing/rates", headers=auth_headers(planning_token), json={
        "dtp_rate": "2", "proof_rate": "1", "ctp_rate": "100", "offset_printing_first_rate": "400",
        "binding_rate": "3",
    })
    assert r.status_code == 403

    mgr_token = login(client, "MGR001", "Manager@123")
    r = client.put("/api/costing/rates", headers=auth_headers(mgr_token), json={
        "dtp_rate": "2", "proof_rate": "1", "ctp_rate": "100", "offset_printing_first_rate": "400",
        "binding_rate": "3",
    })
    assert r.status_code == 200


def test_forecast_reports_insufficient_data_honestly(client, seeded):
    """No fake predictions when there isn't enough history (spec requirement)."""
    material_id = str(seeded["material"].id)
    token = login(client, "STR001", "Store@123")
    r = client.get(f"/api/forecast/materials/{material_id}", headers=auth_headers(token))
    assert r.status_code == 200
    body = r.json()
    assert body["forecast_available"] is False
    assert "Insufficient historical data" in body["message"]


def test_forecast_computes_once_enough_history_exists(client, seeded, db_session):
    from app.models.enums import TxnType
    from app.services.inventory import apply_stock_transaction
    from app.models.user import User
    from datetime import datetime, timedelta

    store_user = db_session.query(User).filter(User.employee_id == "STR001").first()
    material = seeded["material"]
    for i, qty in enumerate([100, 120, 110, 130]):
        txn = apply_stock_transaction(db_session, material_id=material.id, txn_type=TxnType.ISSUE,
                                       quantity=Decimal(qty), user=store_user)
        txn.created_at = datetime.utcnow() - timedelta(days=30 * (4 - i))
    db_session.commit()

    token = login(client, "STR001", "Store@123")
    r = client.get(f"/api/forecast/materials/{material.id}", headers=auth_headers(token))
    body = r.json()
    assert body["forecast_available"] is True
    assert body["predicted_monthly_demand"] > 0
    assert body["confidence"] in ("LOW", "MEDIUM", "HIGH")
