import random
import string
import uuid
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments
from app.models.enums import DepartmentCode, PurchaseOrderStatus, TxnType
from app.models.purchase import Supplier, PurchaseOrder, PurchaseOrderItem, GoodsReceipt
from app.models.user import User
from app.services import audit as audit_service
from app.services.inventory import apply_stock_transaction

router = APIRouter(prefix="/api", tags=["purchasing"])
PURCHASING_DEPTS = require_departments(DepartmentCode.STORE, DepartmentCode.ACCOUNTS)


# ---------------- Schemas (kept local: small, purchasing-only) ----------------
class SupplierIn(BaseModel):
    name: str
    contact_person: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    gst_number: Optional[str] = None


class SupplierOut(SupplierIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    is_active: bool


class POItemIn(BaseModel):
    material_id: uuid.UUID
    quantity_ordered: Decimal
    unit_price: Decimal


class POCreate(BaseModel):
    supplier_id: uuid.UUID
    items: list[POItemIn]
    linked_request_id: Optional[uuid.UUID] = None


class POOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    po_number: str
    supplier_id: uuid.UUID
    status: str
    total_amount: Decimal


class ReceiveLine(BaseModel):
    material_id: uuid.UUID
    quantity_received: Decimal
    unit_price: Decimal


# ---------------- Suppliers ----------------
@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(user: User = Depends(PURCHASING_DEPTS), db: Session = Depends(get_db)):
    return db.query(Supplier).filter(Supplier.is_active == True).order_by(Supplier.name).all()  # noqa: E712


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(payload: SupplierIn, user: User = Depends(PURCHASING_DEPTS), db: Session = Depends(get_db)):
    supplier = Supplier(**payload.model_dump(), created_by=user.id)
    db.add(supplier)
    audit_service.record(db, user=user, action="SUPPLIER_CREATED", entity_type="Supplier")
    db.commit()
    db.refresh(supplier)
    return supplier


# ---------------- Purchase Orders ----------------
@router.get("/purchase-orders", response_model=list[POOut])
def list_pos(user: User = Depends(PURCHASING_DEPTS), db: Session = Depends(get_db)):
    return db.query(PurchaseOrder).order_by(PurchaseOrder.created_at.desc()).all()


@router.post("/purchase-orders", response_model=POOut, status_code=201)
def create_po(payload: POCreate, user: User = Depends(PURCHASING_DEPTS), db: Session = Depends(get_db)):
    if not db.query(Supplier).filter(Supplier.id == payload.supplier_id).first():
        raise HTTPException(status_code=404, detail="Supplier not found")
    po_number = "PO-" + "".join(random.choices(string.digits, k=6))
    total = sum(i.quantity_ordered * i.unit_price for i in payload.items)
    po = PurchaseOrder(po_number=po_number, supplier_id=payload.supplier_id, status=PurchaseOrderStatus.ORDERED,
                        total_amount=total, linked_request_id=payload.linked_request_id, created_by=user.id)
    db.add(po)
    db.flush()
    for item in payload.items:
        db.add(PurchaseOrderItem(po_id=po.id, material_id=item.material_id, quantity_ordered=item.quantity_ordered,
                                  unit_price=item.unit_price))
    audit_service.record(db, user=user, action="PURCHASE_ORDER_CREATED", entity_type="PurchaseOrder", entity_id=po.id)
    db.commit()
    db.refresh(po)
    return po


@router.post("/purchase-orders/{po_id}/receive", response_model=POOut)
async def receive_po(po_id: uuid.UUID, lines: list[ReceiveLine], user: User = Depends(PURCHASING_DEPTS), db: Session = Depends(get_db)):
    """Goods receipt: creates real inventory transactions (never just flips a
    status flag) and updates the PO's received quantities/status."""
    po = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.items)).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    if po.status in (PurchaseOrderStatus.RECEIVED, PurchaseOrderStatus.CANCELLED):
        raise HTTPException(status_code=400, detail=f"PO is {po.status.value}, cannot receive further goods")

    items_by_material = {i.material_id: i for i in po.items}
    for line in lines:
        po_item = items_by_material.get(line.material_id)
        if not po_item:
            raise HTTPException(status_code=400, detail=f"Material {line.material_id} is not on this PO")
        remaining = po_item.quantity_ordered - po_item.quantity_received
        if line.quantity_received > remaining:
            raise HTTPException(status_code=400, detail=f"Cannot receive more than remaining ({remaining})")
        txn = apply_stock_transaction(
            db, material_id=line.material_id, txn_type=TxnType.PURCHASE_RECEIPT, quantity=line.quantity_received,
            user=user, unit_price=line.unit_price, reference_type="PURCHASE_ORDER", reference_id=po.id,
            remarks=f"Goods receipt for {po.po_number}",
        )
        po_item.quantity_received += line.quantity_received
        db.add(GoodsReceipt(po_id=po.id, material_id=line.material_id, quantity_received=line.quantity_received,
                             unit_price=line.unit_price, inventory_transaction_id=txn.id, created_by=user.id))

    all_received = all(i.quantity_received >= i.quantity_ordered for i in po.items)
    po.status = PurchaseOrderStatus.RECEIVED if all_received else PurchaseOrderStatus.PARTIALLY_RECEIVED
    audit_service.record(db, user=user, action="PURCHASE_RECEIVED", entity_type="PurchaseOrder", entity_id=po.id)
    db.commit()
    db.refresh(po)
    from app.ws.manager import manager
    await manager.broadcast("PURCHASE_RECEIVED", {"po_id": str(po.id), "status": po.status.value},
                             visible_to_departments={DepartmentCode.STORE.value, DepartmentCode.ACCOUNTS.value})
    return po
