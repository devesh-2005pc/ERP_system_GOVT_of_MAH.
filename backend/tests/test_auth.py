from tests.conftest import login, auth_headers


def test_login_success(client, seeded):
    token = login(client, "STR001", "Store@123")
    assert token


def test_login_wrong_password_fails(client, seeded):
    r = client.post("/api/auth/login", json={"employee_id": "STR001", "password": "wrong"})
    assert r.status_code == 401


def test_account_lockout_after_repeated_failures(client, seeded):
    for _ in range(5):
        r = client.post("/api/auth/login", json={"employee_id": "STR001", "password": "wrong"})
        assert r.status_code == 401
    # Even the correct password should now be rejected (locked)
    r = client.post("/api/auth/login", json={"employee_id": "STR001", "password": "Store@123"})
    assert r.status_code == 401


def test_me_endpoint_requires_auth(client, seeded):
    r = client.get("/api/auth/me")
    assert r.status_code == 401


def test_me_endpoint_returns_department(client, seeded):
    token = login(client, "STR001", "Store@123")
    r = client.get("/api/auth/me", headers=auth_headers(token))
    assert r.status_code == 200
    assert r.json()["department_code"] == "STORE"


def test_store_cannot_access_purchase_orders_accounts_only_view():
    pass  # covered in test_rbac.py


def test_change_password(client, seeded):
    token = login(client, "STR001", "Store@123")
    r = client.post("/api/auth/change-password", headers=auth_headers(token),
                     json={"current_password": "Store@123", "new_password": "NewPassw0rd!"})
    assert r.status_code == 200
    # old password no longer works
    r = client.post("/api/auth/login", json={"employee_id": "STR001", "password": "Store@123"})
    assert r.status_code == 401
    # new password works
    r = client.post("/api/auth/login", json={"employee_id": "STR001", "password": "NewPassw0rd!"})
    assert r.status_code == 200
