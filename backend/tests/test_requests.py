from tests.conftest import login, auth_headers


def test_full_request_approval_fulfillment_workflow(client, seeded):
    material_id = str(seeded["material"].id)

    planning_token = login(client, "PLN001", "Planning@123")
    r = client.post("/api/material-requests", headers=auth_headers(planning_token),
                     json={"reason": "Job 123", "priority": "HIGH",
                           "items": [{"material_id": material_id, "quantity_requested": "200"}]})
    assert r.status_code == 201
    request_id = r.json()["id"]
    assert r.json()["status"] == "SUBMITTED"

    # Dispatch (unrelated department) cannot see Planning's request
    dispatch_token = login(client, "DSP001", "Dispatch@123")
    r = client.get(f"/api/material-requests/{request_id}", headers=auth_headers(dispatch_token))
    assert r.status_code == 403

    # Store can see and approve it
    store_token = login(client, "STR001", "Store@123")
    r = client.get(f"/api/material-requests/{request_id}", headers=auth_headers(store_token))
    assert r.status_code == 200

    r = client.post(f"/api/material-requests/{request_id}/approve", headers=auth_headers(store_token),
                     json={"decision": "APPROVED"})
    assert r.status_code == 200
    assert r.json()["status"] == "APPROVED"

    # Store fulfills it — this must move REAL stock, not just flip a flag
    before = client.get(f"/api/materials/{material_id}", headers=auth_headers(store_token)).json()
    r = client.post(f"/api/material-requests/{request_id}/fulfill", headers=auth_headers(store_token),
                     json=[{"material_id": material_id, "quantity_to_fulfill": "200"}])
    assert r.status_code == 200
    assert r.json()["status"] == "FULFILLED"
    after = client.get(f"/api/materials/{material_id}", headers=auth_headers(store_token)).json()
    assert float(before["current_stock"]) - float(after["current_stock"]) == 200


def test_planning_only_sees_its_own_requests(client, seeded):
    material_id = str(seeded["material"].id)
    planning_token = login(client, "PLN001", "Planning@123")
    client.post("/api/material-requests", headers=auth_headers(planning_token),
                json={"items": [{"material_id": material_id, "quantity_requested": "10"}]})

    accounts_token = login(client, "ACC001", "Accounts@123")
    r = client.post("/api/material-requests", headers=auth_headers(accounts_token),
                     json={"items": [{"material_id": material_id, "quantity_requested": "5"}]})
    assert r.status_code == 201

    r = client.get("/api/material-requests", headers=auth_headers(planning_token))
    assert r.status_code == 200
    for req in r.json():
        assert req["requesting_department_id"] == str(seeded["departments"][__import__("app.models.enums", fromlist=["DepartmentCode"]).DepartmentCode.PLANNING].id)


def test_cannot_fulfill_more_than_requested(client, seeded):
    material_id = str(seeded["material"].id)
    planning_token = login(client, "PLN001", "Planning@123")
    r = client.post("/api/material-requests", headers=auth_headers(planning_token),
                     json={"items": [{"material_id": material_id, "quantity_requested": "50"}]})
    request_id = r.json()["id"]

    store_token = login(client, "STR001", "Store@123")
    client.post(f"/api/material-requests/{request_id}/approve", headers=auth_headers(store_token), json={"decision": "APPROVED"})
    r = client.post(f"/api/material-requests/{request_id}/fulfill", headers=auth_headers(store_token),
                     json=[{"material_id": material_id, "quantity_to_fulfill": "999"}])
    assert r.status_code == 400
