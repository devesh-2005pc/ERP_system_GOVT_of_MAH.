import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("ENVIRONMENT", "development")

from app.core.database import Base, get_db  # noqa: E402
import app.models  # noqa: F401,E402
from app.main import app as fastapi_app  # noqa: E402
from app.auth.security import hash_password  # noqa: E402
from app.models.user import Department, User  # noqa: E402
from app.models.enums import DepartmentCode  # noqa: E402
from app.models.material import Material  # noqa: E402
from app.models.costing import CostingRateMaster  # noqa: E402


@pytest.fixture()
def db_session(tmp_path):
    db_path = tmp_path / f"test_{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = override_get_db
    session = TestingSessionLocal()
    yield session
    session.close()
    fastapi_app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def client(db_session):
    with TestClient(fastapi_app) as c:
        yield c


@pytest.fixture()
def seeded(db_session):
    depts = {}
    for code in DepartmentCode:
        d = Department(code=code, name=code.value.title())
        db_session.add(d)
        db_session.flush()
        depts[code] = d

    users = {}
    creds = {
        DepartmentCode.MANAGER: ("MGR001", "Manager@123"),
        DepartmentCode.SUB_ADMIN: ("ADM001", "SubAdmin@123"),
        DepartmentCode.STORE: ("STR001", "Store@123"),
        DepartmentCode.PLANNING: ("PLN001", "Planning@123"),
        DepartmentCode.DISPATCH: ("DSP001", "Dispatch@123"),
        DepartmentCode.ACCOUNTS: ("ACC001", "Accounts@123"),
        DepartmentCode.EMPLOYEE: ("EMP001", "Employee@123"),
    }
    for code, (emp_id, pwd) in creds.items():
        u = User(employee_id=emp_id, full_name=emp_id, password_hash=hash_password(pwd),
                 department_id=depts[code].id, must_change_password=False)
        db_session.add(u)
        db_session.flush()
        users[code] = u

    rate_master = CostingRateMaster(
        label="Test Rates", is_active=True, dtp_rate=Decimal("1"), proof_rate=Decimal("1"),
        ctp_rate=Decimal("100"), offset_printing_first_rate=Decimal("400"), binding_rate=Decimal("3"),
        warehouse_loading_pct=Decimal("10"), dispatch_pct=Decimal("2"), book_depot_pct=Decimal("0"),
    )
    db_session.add(rate_master)

    material = Material(sku="TEST-PAPER", name="Test Paper", unit="SHEET", current_stock=Decimal("1000"),
                         minimum_stock=Decimal("100"), reorder_level=Decimal("200"))
    db_session.add(material)
    db_session.commit()
    db_session.refresh(material)

    return {"departments": depts, "users": users, "credentials": creds, "material": material}


def login(client, employee_id, password):
    r = client.post("/api/auth/login", json={"employee_id": employee_id, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}
