"""
Seed the database with departments, demo users, materials, a costing rate
master, and some sample transactions/jobs/suppliers so the system is usable
out of the box for evaluation and development.

*** DEVELOPMENT/DEMO ONLY ***
The printed credentials below are for local evaluation. A production
deployment MUST create its own Manager account with a strong password during
first-run setup (see docs/DEPLOYMENT.md) and this seed script must NOT be run
against a production database.

Run with:  python -m app.seed
"""
from datetime import datetime, timedelta
from decimal import Decimal

from app.core.database import Base, engine, SessionLocal
from app.auth.security import hash_password
from app.models.user import Department, User
from app.models.enums import DepartmentCode, TxnType, MachineStatus, PrintingMethod
from app.models.material import Material, MaterialCategory
from app.models.costing import CostingRateMaster
from app.models.purchase import Supplier
from app.models.press_workflow import Machine
from app.services.inventory import apply_stock_transaction

DEMO_USERS = [
    ("MGR001", "Anil Deshmukh", DepartmentCode.MANAGER, "Manager@123", False),
    ("ADM001", "Sunita Patil", DepartmentCode.SUB_ADMIN, "SubAdmin@123", True),
    ("STR001", "Ramesh Joshi", DepartmentCode.STORE, "Store@123", False),
    ("PLN001", "Kavita Rane", DepartmentCode.PLANNING, "Planning@123", False),
    ("DSP001", "Suresh Pawar", DepartmentCode.DISPATCH, "Dispatch@123", False),
    ("ACC001", "Meena Kulkarni", DepartmentCode.ACCOUNTS, "Accounts@123", False),
    ("EMP001", "Vijay Shinde", DepartmentCode.EMPLOYEE, "Employee@123", False),
    # New department demo users
    ("DIG001", "Priya Naik", DepartmentCode.DIGITAL_PRINTING, "Digital@123", False),
    ("TRD001", "Mohan Gaikwad", DepartmentCode.TRADITIONAL_PRINTING, "Traditional@123", False),
    ("PLT001", "Santosh Mane", DepartmentCode.PLATE_MAKING, "Plate@123", False),
    ("BND001", "Rekha Salvi", DepartmentCode.BINDING, "Binding@123", False),
    ("STD001", "Ganesh Kale", DepartmentCode.STANDARD, "Standard@123", False),
    ("MCH001", "Dinesh Patkar", DepartmentCode.MECHANIC, "Mechanic@123", False),
    ("BIL001", "Anita Bhosale", DepartmentCode.BILLING, "Billing@123", False),
]

DEPARTMENTS = [
    (DepartmentCode.MANAGER, "Manager"),
    (DepartmentCode.SUB_ADMIN, "Subordinate Admin"),
    (DepartmentCode.STORE, "Store"),
    (DepartmentCode.PLANNING, "Planning"),
    (DepartmentCode.DISPATCH, "Dispatch"),
    (DepartmentCode.ACCOUNTS, "Accounts / Budget"),
    (DepartmentCode.EMPLOYEE, "General Employee"),
    # New departments for press workflow
    (DepartmentCode.DIGITAL_PRINTING, "Digital Printing"),
    (DepartmentCode.TRADITIONAL_PRINTING, "Traditional / Offset Printing"),
    (DepartmentCode.PLATE_MAKING, "Plate Making / Pre-Press"),
    (DepartmentCode.BINDING, "Binding and Finishing"),
    (DepartmentCode.STANDARD, "Standard / Quality Checking"),
    (DepartmentCode.MECHANIC, "Mechanic / Machine Maintenance"),
    (DepartmentCode.BILLING, "Billing"),
]

SAMPLE_MACHINES = [
    dict(machine_code="DGT-001", name="HP Indigo 12000 (Digital)", machine_type="Digital Press",
         printing_method=PrintingMethod.DIGITAL, department_code=DepartmentCode.DIGITAL_PRINTING,
         is_color=True, max_paper_size="A3+", supported_gsm_range="60-350",
         status=MachineStatus.AVAILABLE, location="Digital Hall"),
    dict(machine_code="DGT-002", name="Xerox Versant 280 (Digital)", machine_type="Digital Press",
         printing_method=PrintingMethod.DIGITAL, department_code=DepartmentCode.DIGITAL_PRINTING,
         is_color=True, max_paper_size="A3", supported_gsm_range="60-300",
         status=MachineStatus.AVAILABLE, location="Digital Hall"),
    dict(machine_code="OFF-001", name="Komori Lithrone S40 (Offset)", machine_type="Offset Press",
         printing_method=PrintingMethod.KOMORI, department_code=DepartmentCode.TRADITIONAL_PRINTING,
         is_color=True, max_paper_size="70x100cm", supported_gsm_range="50-400",
         max_impressions_per_hour=15000, status=MachineStatus.AVAILABLE, location="Press Hall A"),
    dict(machine_code="OFF-002", name="Heidelberg Speedmaster (Offset)", machine_type="Offset Press",
         printing_method=PrintingMethod.OFFSET, department_code=DepartmentCode.TRADITIONAL_PRINTING,
         is_color=True, max_paper_size="52x74cm", supported_gsm_range="60-300",
         max_impressions_per_hour=12000, status=MachineStatus.AVAILABLE, location="Press Hall B"),
    dict(machine_code="OFF-003", name="Single Colour Offset Press", machine_type="Offset Press",
         printing_method=PrintingMethod.OFFSET, department_code=DepartmentCode.TRADITIONAL_PRINTING,
         is_color=False, max_paper_size="A3", supported_gsm_range="60-250",
         max_impressions_per_hour=8000, status=MachineStatus.AVAILABLE, location="Press Hall C"),
]


def run():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(User).count() > 0:
            print("Database already has users — seed skipped (idempotent).")
            return

        dept_by_code = {}
        for code, name in DEPARTMENTS:
            d = Department(code=code, name=name)
            db.add(d)
            db.flush()
            dept_by_code[code] = d

        system_user = None
        for emp_id, name, dept_code, pwd, is_admin in DEMO_USERS:
            u = User(
                employee_id=emp_id, full_name=name, email=f"{emp_id.lower()}@mudranalaya.local",
                password_hash=hash_password(pwd), department_id=dept_by_code[dept_code].id,
                is_department_admin=is_admin, must_change_password=True,
            )
            db.add(u)
            db.flush()
            if dept_code == DepartmentCode.MANAGER:
                system_user = u
        db.commit()

        # Costing rate master
        rate_master = CostingRateMaster(
            label="Default Rate Master", is_active=True,
            dtp_rate=Decimal("1.50"), proof_rate=Decimal("0.75"), ctp_rate=Decimal("120.00"),
            offset_printing_first_rate=Decimal("450.00"), binding_rate=Decimal("3.20"),
            warehouse_loading_pct=Decimal("15"), dispatch_pct=Decimal("3"), book_depot_pct=Decimal("1"),
            created_by=system_user.id,
        )
        db.add(rate_master)

        # Suppliers
        s1 = Supplier(name="Nashik Paper Mills Pvt Ltd", contact_person="R. Deshpande", phone="9876543210",
                       email="sales@nashikpaper.example", gst_number="27ABCDE1234F1Z5", created_by=system_user.id)
        s2 = Supplier(name="Western Inks & Chemicals", contact_person="P. Kale", phone="9823456789",
                       email="orders@westerninks.example", gst_number="27FGHIJ5678K1Z9", created_by=system_user.id)
        db.add_all([s1, s2])
        db.flush()

        # Materials
        materials_data = [
            dict(sku="PPR-A4-70", name="A4 Paper 70 GSM", unit="SHEET", gsm="70", minimum_stock=2000,
                 reorder_level=3000, reorder_quantity=10000, purchase_price=Decimal("0.85"),
                 storage_location="Rack A1", preferred_supplier_id=s1.id, opening=8500),
            dict(sku="PPR-A3-90", name="A3 Paper 90 GSM", unit="SHEET", gsm="90", minimum_stock=1000,
                 reorder_level=1500, reorder_quantity=5000, purchase_price=Decimal("1.40"),
                 storage_location="Rack A2", preferred_supplier_id=s1.id, opening=4200),
            dict(sku="PPR-ART-130", name="Art Paper 130 GSM", unit="SHEET", gsm="130", minimum_stock=500,
                 reorder_level=800, reorder_quantity=3000, purchase_price=Decimal("2.10"),
                 storage_location="Rack A3", preferred_supplier_id=s1.id, opening=1900),
            dict(sku="INK-CYN", name="Offset Ink - Cyan", unit="L", minimum_stock=5, reorder_level=8,
                 reorder_quantity=20, purchase_price=Decimal("650.00"), storage_location="Ink Store",
                 preferred_supplier_id=s2.id, opening=14),
            dict(sku="INK-MAG", name="Offset Ink - Magenta", unit="L", minimum_stock=5, reorder_level=8,
                 reorder_quantity=20, purchase_price=Decimal("650.00"), storage_location="Ink Store",
                 preferred_supplier_id=s2.id, opening=6),
            dict(sku="PLATE-CTP", name="CTP Printing Plate", unit="PCS", minimum_stock=20, reorder_level=30,
                 reorder_quantity=100, purchase_price=Decimal("180.00"), storage_location="Rack B1",
                 preferred_supplier_id=s2.id, opening=65),
            dict(sku="BIND-WIRE", name="Binding Wire", unit="KG", minimum_stock=10, reorder_level=15,
                 reorder_quantity=50, purchase_price=Decimal("210.00"), storage_location="Rack B2",
                 preferred_supplier_id=s2.id, opening=32),
        ]

        materials = []
        for md in materials_data:
            opening = md.pop("opening")
            m = Material(**md, current_stock=Decimal("0"), created_by=system_user.id, updated_by=system_user.id)
            db.add(m)
            db.flush()
            materials.append((m, opening))

        db.commit()

        # Opening stock + a few months of synthetic-but-labeled ISSUE history so
        # forecasting has something real to compute against. Backdated
        # timestamps are set directly for demo realism; a live system will
        # naturally accumulate real ledger history going forward.
        store_user = db.query(User).filter(User.employee_id == "STR001").first()
        for m, opening in materials:
            apply_stock_transaction(db, material_id=m.id, txn_type=TxnType.OPENING, quantity=Decimal(opening),
                                     user=store_user, remarks="Initial opening stock (seed)")

        # Backdated monthly issue history for the A4 paper item, for a
        # realistic forecasting demo.
        a4 = materials[0][0]
        history_qty = [800, 950, 870, 1020, 1100, 1050]
        for i, qty in enumerate(reversed(history_qty)):
            txn = apply_stock_transaction(
                db, material_id=a4.id, txn_type=TxnType.ISSUE, quantity=Decimal(qty),
                user=store_user, remarks="Seed historical consumption",
            )
            txn.created_at = datetime.utcnow() - timedelta(days=30 * (len(history_qty) - i))
        db.commit()

        # Seed sample machines (idempotent check)
        if db.query(Machine).count() == 0:
            for md in SAMPLE_MACHINES:
                m = Machine(**md, created_by=system_user.id if system_user else None)
                db.add(m)
            db.commit()
            print(f"  Seeded {len(SAMPLE_MACHINES)} sample machines.")

        print("Seed complete.")
        print("\n=== DEVELOPMENT-ONLY LOGIN CREDENTIALS (do not use in production) ===")
        for emp_id, name, dept_code, pwd, _ in DEMO_USERS:
            print(f"  {dept_code.value:25s}  employee_id={emp_id:8s}  password={pwd}")
        print("=======================================================================\n")
    finally:
        db.close()


if __name__ == "__main__":
    run()
