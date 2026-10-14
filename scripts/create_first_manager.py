#!/usr/bin/env python3
"""
Create the first Manager account for a PRODUCTION deployment.

Unlike app/seed.py (which is for development/demo only and creates known
weak passwords), this script is meant to be run once on a fresh production
database and will prompt for a strong password interactively (so it never
appears in shell history or process listings).

Usage (run from the backend/ directory with the venv activated):
    python ../scripts/create_first_manager.py
"""
import getpass
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import Base, engine, SessionLocal  # noqa: E402
import app.models  # noqa: F401,E402
from app.auth.security import hash_password  # noqa: E402
from app.models.user import Department, User  # noqa: E402
from app.models.enums import DepartmentCode  # noqa: E402

DEPARTMENTS = [
    (DepartmentCode.MANAGER, "Manager"), (DepartmentCode.SUB_ADMIN, "Subordinate Admin"),
    (DepartmentCode.STORE, "Store"), (DepartmentCode.PLANNING, "Planning"),
    (DepartmentCode.DISPATCH, "Dispatch"), (DepartmentCode.ACCOUNTS, "Accounts / Budget"),
    (DepartmentCode.EMPLOYEE, "General Employee"),
]

PASSWORD_MIN_LENGTH = 10


def validate_password(pw: str) -> str | None:
    if len(pw) < PASSWORD_MIN_LENGTH:
        return f"Password must be at least {PASSWORD_MIN_LENGTH} characters"
    if not re.search(r"[A-Z]", pw) or not re.search(r"[a-z]", pw) or not re.search(r"\d", pw):
        return "Password must contain upper case, lower case, and a digit"
    return None


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing_manager = (
            db.query(User).join(Department).filter(Department.code == DepartmentCode.MANAGER).first()
        )
        if existing_manager:
            print(f"A Manager account already exists: {existing_manager.employee_id}. Aborting.")
            return

        for code, name in DEPARTMENTS:
            if not db.query(Department).filter(Department.code == code).first():
                db.add(Department(code=code, name=name))
        db.commit()

        print("=== Mudranalaya ERP-MIS: First Manager Setup ===")
        employee_id = input("Manager Employee ID (e.g. MGR001): ").strip()
        full_name = input("Full Name: ").strip()
        email = input("Email (optional): ").strip() or None

        while True:
            pw1 = getpass.getpass("Password: ")
            issue = validate_password(pw1)
            if issue:
                print("  " + issue)
                continue
            pw2 = getpass.getpass("Confirm Password: ")
            if pw1 != pw2:
                print("  Passwords do not match, try again.")
                continue
            break

        manager_dept = db.query(Department).filter(Department.code == DepartmentCode.MANAGER).first()
        user = User(
            employee_id=employee_id, full_name=full_name, email=email,
            password_hash=hash_password(pw1), department_id=manager_dept.id,
            must_change_password=False,
        )
        db.add(user)
        db.commit()
        print(f"\nManager account '{employee_id}' created successfully. You can now log in.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
