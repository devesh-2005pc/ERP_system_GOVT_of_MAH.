"""
Billing Department API — work order lookup + Excel bill generation.
BILLING department searches work orders and generates Excel bills.
The official government Excel template is configurable (mappable when provided).
"""
import io
import random
import string
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import require_departments
from app.models.enums import DepartmentCode, BillingStatus, JobStatus
from app.models.production import ProductionJob, DispatchOrder
from app.models.press_workflow import BillingRecord, ProductionBatch, PlanningAssignment, Machine
from app.models.costing import CostEstimate
from app.models.user import User
from app.services import audit as audit_service

router = APIRouter(prefix="/api/billing", tags=["billing"])

BILLING_DEPT = require_departments(DepartmentCode.BILLING)
BILLING_OR_ACCOUNTS = require_departments(DepartmentCode.BILLING, DepartmentCode.ACCOUNTS)


class BillGenerateRequest(BaseModel):
    billing_quantity: Optional[int] = None
    billing_amount: Optional[Decimal] = None
    cost_estimate_id: Optional[uuid.UUID] = None
    remarks: Optional[str] = None


class BillingRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    job_id: uuid.UUID
    bill_reference: str
    billing_quantity: Optional[int] = None
    billing_amount: Optional[Decimal] = None
    status: str
    remarks: Optional[str] = None
    generated_at: datetime
    file_path: Optional[str] = None


class WorkOrderBillingView(BaseModel):
    """Full billing view of a work order."""
    job_id: str
    job_number: str
    client_name: str
    work_name: str
    pages: Optional[int] = None
    copies: Optional[int] = None
    priority: str
    status: str
    deadline: Optional[str] = None

    # Quantity summary
    total_produced: int
    total_dispatched: int
    remaining_production: int

    # Machine/planning
    machine_name: Optional[str] = None
    printing_method: Optional[str] = None
    financial_year: Optional[str] = None

    # Billing history
    billing_records: list[BillingRecordOut]
    total_billed_quantity: int
    billing_status: str


def _gen_bill_ref(db: Session) -> str:
    suffix = "".join(random.choices(string.digits, k=8))
    return f"BILL-{suffix}"


def _get_job_billing_view(db: Session, job: ProductionJob) -> dict:
    """Build the billing view dict for a work order."""
    # Produced quantity (from completed batches)
    total_produced = int(db.query(func.coalesce(func.sum(ProductionBatch.quantity_produced), 0)).filter(
        ProductionBatch.job_id == job.id,
        ProductionBatch.is_complete == True,  # noqa: E712
    ).scalar() or 0)

    # Dispatched quantity
    total_dispatched = int(db.query(func.coalesce(func.sum(DispatchOrder.quantity), 0)).filter(
        DispatchOrder.job_id == job.id,
    ).scalar() or 0)

    # Latest planning assignment
    assignment = db.query(PlanningAssignment).filter(
        PlanningAssignment.job_id == job.id,
    ).order_by(PlanningAssignment.created_at.desc()).first()

    machine_name = None
    printing_method = None
    financial_year = None
    if assignment:
        printing_method = assignment.printing_method.value if assignment.printing_method else None
        financial_year = assignment.financial_year
        if assignment.machine_id:
            machine = db.query(Machine).filter(Machine.id == assignment.machine_id).first()
            machine_name = machine.name if machine else None

    # Billing records
    billing_records = db.query(BillingRecord).filter(BillingRecord.job_id == job.id).order_by(BillingRecord.generated_at.desc()).all()
    total_billed = sum(r.billing_quantity or 0 for r in billing_records)

    # Overall billing status
    if not billing_records:
        billing_status = BillingStatus.PENDING.value
    elif total_billed >= (job.copies or 0) and job.copies:
        billing_status = BillingStatus.BILLED.value
    else:
        billing_status = BillingStatus.PARTIALLY_BILLED.value

    return {
        "job_id": str(job.id),
        "job_number": job.job_number,
        "client_name": job.client_name,
        "work_name": job.work_name,
        "pages": job.pages,
        "copies": job.copies,
        "priority": job.priority,
        "status": job.status.value,
        "deadline": job.deadline.isoformat() if job.deadline else None,
        "total_produced": total_produced,
        "total_dispatched": total_dispatched,
        "remaining_production": max(0, (job.copies or 0) - total_produced),
        "machine_name": machine_name,
        "printing_method": printing_method,
        "financial_year": financial_year,
        "billing_records": billing_records,
        "total_billed_quantity": total_billed,
        "billing_status": billing_status,
    }


@router.get("/search")
def search_work_orders(
    q: str = Query(min_length=1, description="Work order number, client name, or job description"),
    user: User = Depends(BILLING_DEPT),
    db: Session = Depends(get_db),
):
    """Search work orders by job number, client name, or work name for billing."""
    jobs = db.query(ProductionJob).filter(
        (ProductionJob.job_number.ilike(f"%{q}%")) |
        (ProductionJob.client_name.ilike(f"%{q}%")) |
        (ProductionJob.work_name.ilike(f"%{q}%"))
    ).order_by(ProductionJob.created_at.desc()).limit(20).all()

    results = []
    for job in jobs:
        total_produced = int(db.query(func.coalesce(func.sum(ProductionBatch.quantity_produced), 0)).filter(
            ProductionBatch.job_id == job.id, ProductionBatch.is_complete == True  # noqa: E712
        ).scalar() or 0)
        bill_count = db.query(func.count(BillingRecord.id)).filter(BillingRecord.job_id == job.id).scalar()
        results.append({
            "id": str(job.id),
            "job_number": job.job_number,
            "client_name": job.client_name,
            "work_name": job.work_name,
            "copies": job.copies,
            "status": job.status.value,
            "total_produced": total_produced,
            "bill_count": bill_count,
        })
    return results


@router.get("/job/{job_id}", response_model=WorkOrderBillingView)
def get_billing_detail(job_id: uuid.UUID, user: User = Depends(BILLING_DEPT), db: Session = Depends(get_db)):
    """Full billing view of a work order — all relevant data for bill generation."""
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Work order not found")
    return _get_job_billing_view(db, job)


@router.get("/job/{job_id}/records", response_model=list[BillingRecordOut])
def list_billing_records(job_id: uuid.UUID, user: User = Depends(BILLING_OR_ACCOUNTS), db: Session = Depends(get_db)):
    return db.query(BillingRecord).filter(BillingRecord.job_id == job_id).order_by(BillingRecord.generated_at.desc()).all()


@router.post("/job/{job_id}/generate", status_code=201)
async def generate_bill(
    job_id: uuid.UUID,
    payload: BillGenerateRequest,
    user: User = Depends(BILLING_DEPT),
    db: Session = Depends(get_db),
):
    """
    Generate a bill for a work order.
    Creates a BillingRecord and returns a downloadable Excel file.

    The government billing Excel template should be placed at:
    data/billing_template.xlsx

    Until the official template is provided, a structured data export is generated.
    Template mapping fields are documented below for integration.
    """
    job = db.query(ProductionJob).filter(ProductionJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Work order not found")

    # Duplicate guard: prevent identical bill without explicit override
    existing_bills = db.query(BillingRecord).filter(BillingRecord.job_id == job_id).count()
    if existing_bills > 0 and payload.billing_quantity == (job.copies or 0):
        # Check if a full-quantity bill already exists
        full_bill = db.query(BillingRecord).filter(
            BillingRecord.job_id == job_id,
            BillingRecord.billing_quantity == job.copies,
        ).first()
        if full_bill:
            raise HTTPException(
                status_code=409,
                detail=f"A full-quantity bill (reference: {full_bill.bill_reference}) already exists for this work order. "
                       "If a partial/additional bill is required, specify a different billing_quantity."
            )

    view = _get_job_billing_view(db, job)
    billing_qty = payload.billing_quantity or view["total_produced"]

    # Fetch cost estimate if provided
    cost_estimate = None
    if payload.cost_estimate_id:
        cost_estimate = db.query(CostEstimate).filter(CostEstimate.id == payload.cost_estimate_id).first()

    bill_ref = _gen_bill_ref(db)

    # Create billing record FIRST (before file generation)
    bill = BillingRecord(
        job_id=job_id,
        bill_reference=bill_ref,
        generated_by=user.id,
        billing_quantity=billing_qty,
        billing_amount=payload.billing_amount or (cost_estimate.final_landed_billing_cost if cost_estimate else None),
        status=BillingStatus.BILLED,
        cost_estimate_id=payload.cost_estimate_id,
        remarks=payload.remarks,
        generated_at=datetime.utcnow(),
        created_by=user.id,
    )
    db.add(bill)
    audit_service.record(
        db, user=user, action="BILL_GENERATED", entity_type="BillingRecord",
        detail=f"Job: {job.job_number}, Ref: {bill_ref}, Qty: {billing_qty}",
    )
    db.commit()
    db.refresh(bill)

    # Generate Excel file
    excel_bytes = _generate_bill_excel(view, bill, billing_qty, cost_estimate)

    # Stream back
    filename = f"{bill_ref}_{job.job_number}.xlsx"
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _generate_bill_excel(view: dict, bill: BillingRecord, billing_qty: int, cost_estimate) -> bytes:
    """
    Generate the billing Excel file.

    TEMPLATE INTEGRATION NOTES:
    When the official government billing template (Excel) is provided:
    1. Load template: wb = openpyxl.load_workbook('data/billing_template.xlsx')
    2. Map fields to specific cells as per the template layout.
    3. Replace the dynamic workbook creation below with template-based population.
    4. Preserve all existing formulas, merged cells, print layout, and formatting.

    Field mapping reference (map these to template cells):
    - Bill Reference     -> view["job_number"] + bill.bill_reference
    - Client/Department  -> view["client_name"]
    - Work Description   -> view["work_name"]
    - Pages              -> view["pages"]
    - Ordered Copies     -> view["copies"]
    - Billing Quantity   -> billing_qty
    - Produced Quantity  -> view["total_produced"]
    - Dispatched Qty     -> view["total_dispatched"]
    - Machine Used       -> view["machine_name"]
    - Printing Method    -> view["printing_method"]
    - Financial Year     -> view["financial_year"]
    - Billing Amount     -> bill.billing_amount
    - Generated Date     -> bill.generated_at
    - Generated By       -> (bill.generated_by user info)
    - Cost breakdown     -> from cost_estimate if available
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl library not available")

    wb = Workbook()
    ws = wb.active
    ws.title = "Bill"

    # Set column widths
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18

    header_font = Font(bold=True, size=12)
    title_font = Font(bold=True, size=14)
    center = Alignment(horizontal="center")
    right = Alignment(horizontal="right")

    # Header block
    ws.merge_cells("A1:D1")
    ws["A1"] = "GOVERNMENT PRINTING PRESS"
    ws["A1"].font = Font(bold=True, size=16)
    ws["A1"].alignment = center

    ws.merge_cells("A2:D2")
    ws["A2"] = "Mudranalaya ERP-MIS — Print Job Bill"
    ws["A2"].font = title_font
    ws["A2"].alignment = center

    ws.merge_cells("A3:D3")
    ws["A3"] = f"Bill Reference: {bill.bill_reference}    Date: {bill.generated_at.strftime('%d/%m/%Y')}"
    ws["A3"].alignment = center

    # Work order details
    ws["A5"] = "Work Order Number"
    ws["B5"] = view["job_number"]
    ws["A6"] = "Client / Department"
    ws["B6"] = view["client_name"]
    ws["A7"] = "Job Description"
    ws["B7"] = view["work_name"]
    ws["A8"] = "Pages"
    ws["B8"] = view["pages"] or ""
    ws["A9"] = "Ordered Copies"
    ws["B9"] = view["copies"] or ""
    ws["A10"] = "Priority"
    ws["B10"] = view["priority"]
    ws["A11"] = "Deadline"
    ws["B11"] = view["deadline"] or ""
    ws["A12"] = "Machine Used"
    ws["B12"] = view["machine_name"] or "Not assigned"
    ws["A13"] = "Printing Method"
    ws["B13"] = view["printing_method"] or ""
    ws["A14"] = "Financial Year"
    ws["B14"] = view["financial_year"] or ""

    # Quantity summary
    ws["A16"] = "QUANTITY SUMMARY"
    ws["A16"].font = header_font
    ws["A17"] = "Total Produced"
    ws["B17"] = view["total_produced"]
    ws["A18"] = "Total Dispatched"
    ws["B18"] = view["total_dispatched"]
    ws["A19"] = "Remaining Production"
    ws["B19"] = view["remaining_production"]
    ws["A20"] = "Billing Quantity (this bill)"
    ws["B20"] = billing_qty
    ws["B20"].font = Font(bold=True)

    # Cost summary
    ws["A22"] = "COST SUMMARY"
    ws["A22"].font = header_font
    if cost_estimate:
        ws["A23"] = "Final Landed Billing Cost"
        ws["B23"] = float(cost_estimate.final_landed_billing_cost)
        ws["A24"] = "Per Copy Rate"
        ws["B24"] = float(cost_estimate.per_copy_rate)
    ws["A25"] = "Billing Amount"
    ws["B25"] = float(bill.billing_amount) if bill.billing_amount else "To be determined"
    ws["B25"].font = Font(bold=True)

    # Billing remarks
    ws["A27"] = "Remarks"
    ws["B27"] = bill.remarks or ""

    # Footer
    ws["A29"] = "NOTE: This is a system-generated bill. Official government billing template integration pending."
    ws["A29"].font = Font(italic=True, size=9, color="888888")

    ws["A30"] = "Template Integration: Place official Excel template at data/billing_template.xlsx"
    ws["A30"].font = Font(italic=True, size=9, color="888888")

    # Make header rows bold
    for row in [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]:
        ws[f"A{row}"].font = Font(bold=True)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
