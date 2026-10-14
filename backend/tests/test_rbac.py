from tests.conftest import login, auth_headers


def test_dispatch_cannot_see_purchase_orders(client, seeded):
    token = login(client, "DSP001", "Dispatch@123")
    r = client.get("/api/purchase-orders", headers=auth_headers(token))
    assert r.status_code == 403


def test_dispatch_can_see_its_own_dispatch_endpoint(client, seeded):
    token = login(client, "DSP001", "Dispatch@123")
    r = client.get("/api/dispatch", headers=auth_headers(token))
    assert r.status_code == 200


def test_planning_cannot_see_dispatch(client, seeded):
    token = login(client, "PLN001", "Planning@123")
    r = client.get("/api/dispatch", headers=auth_headers(token))
    assert r.status_code == 403


def test_planning_cannot_see_accounts_budgets(client, seeded):
    token = login(client, "PLN001", "Planning@123")
    r = client.get("/api/accounts/budgets", headers=auth_headers(token))
    assert r.status_code == 403


def test_store_cannot_see_accounts_expenses(client, seeded):
    token = login(client, "STR001", "Store@123")
    r = client.get("/api/accounts/expenses", headers=auth_headers(token))
    assert r.status_code == 403


def test_store_cannot_edit_dispatch(client, seeded):
    token = login(client, "STR001", "Store@123")
    r = client.post("/api/dispatch", headers=auth_headers(token),
                     json={"recipient": "Someone", "quantity": 5})
    assert r.status_code == 403


def test_employee_has_no_department_wide_access(client, seeded):
    token = login(client, "EMP001", "Employee@123")
    for path in ["/api/purchase-orders", "/api/dispatch", "/api/accounts/budgets", "/api/inventory/transactions"]:
        r = client.get(path, headers=auth_headers(token))
        assert r.status_code == 403, f"Employee should not access {path}"


def test_manager_can_access_every_department(client, seeded):
    token = login(client, "MGR001", "Manager@123")
    for path in ["/api/purchase-orders", "/api/dispatch", "/api/accounts/budgets", "/api/inventory/transactions"]:
        r = client.get(path, headers=auth_headers(token))
        assert r.status_code == 200, f"Manager should access {path}, got {r.status_code}: {r.text}"


def test_sub_admin_can_access_every_department(client, seeded):
    token = login(client, "ADM001", "SubAdmin@123")
    for path in ["/api/purchase-orders", "/api/dispatch", "/api/accounts/budgets", "/api/inventory/transactions"]:
        r = client.get(path, headers=auth_headers(token))
        assert r.status_code == 200, f"Sub-Admin should access {path}, got {r.status_code}: {r.text}"


def test_only_manager_can_deactivate_user_not_subadmin(client, seeded):
    admin_token = login(client, "ADM001", "SubAdmin@123")
    target_id = seeded["users"][__import__("app.models.enums", fromlist=["DepartmentCode"]).DepartmentCode.EMPLOYEE].id
    r = client.delete(f"/api/users/{target_id}", headers=auth_headers(admin_token))
    assert r.status_code == 403

    mgr_token = login(client, "MGR001", "Manager@123")
    r = client.delete(f"/api/users/{target_id}", headers=auth_headers(mgr_token))
    assert r.status_code == 200


def test_all_departments_can_read_shared_material_catalog(client, seeded):
    """Materials catalog + stock headline is intentionally shared read-access
    (Planning needs availability visibility) even though the ledger isn't."""
    for emp_id, pwd in [("STR001", "Store@123"), ("PLN001", "Planning@123"), ("DSP001", "Dispatch@123"),
                        ("ACC001", "Accounts@123"), ("EMP001", "Employee@123")]:
        token = login(client, emp_id, pwd)
        r = client.get("/api/materials", headers=auth_headers(token))
        assert r.status_code == 200, f"{emp_id} should read the materials catalog"


def test_only_store_can_write_materials(client, seeded):
    token = login(client, "PLN001", "Planning@123")
    r = client.post("/api/materials", headers=auth_headers(token),
                     json={"sku": "X-1", "name": "X"})
    assert r.status_code == 403

    token = login(client, "STR001", "Store@123")
    r = client.post("/api/materials", headers=auth_headers(token),
                     json={"sku": "X-1", "name": "X"})
    assert r.status_code == 201
