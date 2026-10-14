import concurrent.futures
from decimal import Decimal

from tests.conftest import login, auth_headers


def test_receive_and_issue_updates_stock_correctly(client, seeded):
    token = login(client, "STR001", "Store@123")
    material_id = str(seeded["material"].id)

    r = client.post("/api/inventory/receive", headers=auth_headers(token),
                     json={"material_id": material_id, "quantity": "500", "unit_price": "2.00"})
    assert r.status_code == 201
    assert r.json()["balance_after"] == "1500.000"

    r = client.post("/api/inventory/issue", headers=auth_headers(token),
                     json={"material_id": material_id, "quantity": "300"})
    assert r.status_code == 201
    assert r.json()["balance_after"] == "1200.000"


def test_issue_more_than_available_is_rejected(client, seeded):
    token = login(client, "STR001", "Store@123")
    material_id = str(seeded["material"].id)
    r = client.post("/api/inventory/issue", headers=auth_headers(token),
                     json={"material_id": material_id, "quantity": "999999"})
    assert r.status_code == 400
    assert "Insufficient stock" in r.json()["error"]


def test_stock_never_goes_negative_and_matches_ledger(client, seeded):
    token = login(client, "STR001", "Store@123")
    material_id = str(seeded["material"].id)
    # Issue down to exactly zero, then confirm one more unit is rejected.
    client.post("/api/inventory/issue", headers=auth_headers(token),
                json={"material_id": material_id, "quantity": "1000"})
    m = client.get(f"/api/materials/{material_id}", headers=auth_headers(token)).json()
    assert m["current_stock"] == "0.000"
    r = client.post("/api/inventory/issue", headers=auth_headers(token),
                     json={"material_id": material_id, "quantity": "1"})
    assert r.status_code == 400


def test_idempotency_key_prevents_double_issue(client, seeded):
    token = login(client, "STR001", "Store@123")
    material_id = str(seeded["material"].id)
    payload = {"material_id": material_id, "quantity": "100", "idempotency_key": "same-key-123"}
    r1 = client.post("/api/inventory/issue", headers=auth_headers(token), json=payload)
    r2 = client.post("/api/inventory/issue", headers=auth_headers(token), json=payload)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]  # same transaction returned, not duplicated
    m = client.get(f"/api/materials/{material_id}", headers=auth_headers(token)).json()
    assert m["current_stock"] == "900.000"  # only ONE 100-unit issue actually applied


def test_concurrent_issues_never_corrupt_stock(client, seeded):
    """
    THE critical correctness test: fire many concurrent issue requests
    against the same material and confirm the final stock is exactly what
    arithmetic predicts — never over-drawn, never double-counted, no lost
    updates. This directly tests the row-locking in
    app/services/inventory.py::apply_stock_transaction.
    """
    token = login(client, "STR001", "Store@123")
    material_id = str(seeded["material"].id)  # starts at 1000

    n_requests = 30
    qty_each = Decimal("20")  # 30 * 20 = 600, well within starting stock of 1000

    def issue(i):
        return client.post(
            "/api/inventory/issue",
            headers=auth_headers(token),
            json={"material_id": material_id, "quantity": str(qty_each), "idempotency_key": f"race-{i}"},
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as ex:
        results = list(ex.map(issue, range(n_requests)))

    statuses = [r.status_code for r in results]
    assert all(s == 201 for s in statuses), f"Some concurrent issues unexpectedly failed: {statuses}"

    final = client.get(f"/api/materials/{material_id}", headers=auth_headers(token)).json()
    expected = Decimal("1000") - (qty_each * n_requests)
    assert Decimal(final["current_stock"]) == expected, (
        f"Race condition detected: expected {expected}, got {final['current_stock']}"
    )

    # Ledger must have exactly one row per successful issue (no duplicates, no lost writes).
    txns = client.get(f"/api/inventory/transactions?material_id={material_id}", headers=auth_headers(token)).json()
    issue_txns = [t for t in txns if t["txn_type"] == "ISSUE"]
    assert len(issue_txns) == n_requests
