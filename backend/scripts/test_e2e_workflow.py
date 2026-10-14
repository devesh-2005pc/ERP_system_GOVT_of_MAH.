import os
import sys
import json
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.main import app
from app.core.database import SessionLocal
from app.models.user import User
from app.models.enums import DepartmentCode
from app.models.press_workflow import Machine

def setup_test_data():
    db = SessionLocal()
    # Ensure manager user exists
    user = db.query(User).filter(User.employee_id == "MGR001").first()
    if not user:
        from app.core.security import get_password_hash
        user = User(
            employee_id="MGR001",
            full_name="Manager User",
            email="manager@test.com",
            hashed_password=get_password_hash("Manager@123"),
            department_code=DepartmentCode.MANAGER,
            is_active=True
        )
        db.add(user)
        db.commit()
    
    # Ensure a machine exists
    machine = db.query(Machine).filter(Machine.name == "Test Machine").first()
    if not machine:
        machine = Machine(
            name="Test Machine",
            machine_code="TM-01",
            machine_type="OFFSET",
            printing_method="OFFSET",
            is_color=True,
            status="AVAILABLE"
        )
        db.add(machine)
        db.commit()
        db.refresh(machine)
    
    machine_id = machine.id
    db.close()
    return machine_id

def run_test():
    machine_id = setup_test_data()
    client = TestClient(app)
    
    print("1. Login as MGR001")
    response = client.post("/api/auth/login", json={"employee_id": "MGR001", "password": "Manager@123"})
    assert response.status_code in [200, 201], f"Login failed: {response.text}"
    token = response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    print("2. Create WO-TEST-001")
    response = client.post("/api/production/jobs", json={
        "client_name": "Test Client",
        "work_name": "Test Publication",
        "pages": 100,
        "copies": 5000,
        "priority": "HIGH"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Create WO failed: {response.text}"
    job_id = response.json()["id"]
    job_number = response.json()["job_number"]
    print(f"Created job {job_number} (ID: {job_id})")
    
    print("3. Plan WO")
    response = client.post(f"/api/planning/jobs/{job_id}/assign", json={
        "printing_method": "OFFSET",
        "department_code": "TRADITIONAL_PRINTING",
        "machine_id": str(machine_id),
        "plate_required": False,
        "financial_year": "2025-26",
        "paper_quantity_required": 5500
    }, headers=headers)
    assert response.status_code in [200, 201], f"Planning failed: {response.text}"
    
    print("4. Partially produce")
    response = client.post(f"/api/planning/jobs/{job_id}/batches", json={
        "quantity_produced": 2000,
        "financial_year": "2025-26"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Batch failed: {response.text}"
    
    print("5. Pause")
    response = client.post(f"/api/planning/jobs/{job_id}/pause", json={
        "reason": "Machine breakdown"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Pause failed: {response.text}"
    
    # Check status is PAUSED
    response = client.get(f"/api/planning/jobs/{job_id}/detail", headers=headers)
    assert response.json()["status"] == "PAUSED", "Status should be PAUSED"
    
    print("6. Resume")
    response = client.post(f"/api/planning/jobs/{job_id}/resume", json={
        "remarks": "Fixed"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Resume failed: {response.text}"
    
    print("7. Complete production")
    response = client.post(f"/api/planning/jobs/{job_id}/batches", json={
        "quantity_produced": 3000,
        "financial_year": "2025-26"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Batch 2 failed: {response.text}"
    
    # Check status is COMPLETED
    response = client.get(f"/api/planning/jobs/{job_id}/detail", headers=headers)
    assert response.json()["status"] == "COMPLETED", f"Status should be COMPLETED, got {response.json()['status']}"
    
    print("8. Binding")
    response = client.post(f"/api/binding/job/{job_id}", json={
        "finishing_method": "PERFECT_BINDING",
        "quantity_received": 5000
    }, headers=headers)
    assert response.status_code in [200, 201], f"Start Binding failed: {response.text}"
    finishing_id = response.json()["id"]
    
    response = client.put(f"/api/binding/{finishing_id}", json={
        "quantity_completed": 5000,
        "is_complete": True
    }, headers=headers)
    assert response.status_code in [200, 201], f"Complete Binding failed: {response.text}"
    
    print("9. Standard Inspection")
    response = client.post(f"/api/standard/job/{job_id}", json={
        "quantity_inspected": 5000,
        "packaging_ok": True,
        "quantity_ok": True
    }, headers=headers)
    assert response.status_code in [200, 201], f"Inspection failed: {response.text}"
    insp_id = response.json()["id"]
    
    response = client.put(f"/api/standard/{insp_id}/decide", json={
        "status": "PASSED"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Inspection Decide failed: {response.text}"
    
    print("10. Dispatch")
    # Our dispatch module doesn't strictly link to jobs via ID yet, but let's create a generic dispatch order
    response = client.post("/api/dispatch", json={
        "recipient": "Test Client",
        "quantity": 5000,
        "vehicle_or_courier": "Truck 1"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Dispatch failed: {response.text}"
    
    # Update job directly for dispatched_quantity - wait, Standard inspection passed status marks it ready for dispatch.
    
    print("11. Billing")
    # For billing to generate correctly, we might need a billing rate. Let's see if generate works
    response = client.post(f"/api/billing/job/{job_id}/generate", json={
        "billing_quantity": 5000,
        "billing_amount": 100000.0,
        "remarks": "Final bill"
    }, headers=headers)
    assert response.status_code in [200, 201], f"Billing failed: {response.text}"
    
    print("End-to-End test passed successfully!")

if __name__ == "__main__":
    run_test()
