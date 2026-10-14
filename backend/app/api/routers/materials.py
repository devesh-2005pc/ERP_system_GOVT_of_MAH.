import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import get_current_user, require_departments, is_cross_department
from app.models.enums import DepartmentCode, TxnType
from app.models.material import Material, InventoryTransaction
from app.models.user import User
from app.schemas.material import (
    MaterialCreate, MaterialUpdate, MaterialOut, StockTxnRequest, InventoryTxnOut,
)
from app.services.inventory import apply_stock_transaction, InsufficientStockError
from app.services import audit as audit_service
from app.ws.manager import manager

router = APIRouter(prefix="/api/materials", tags=["materials"])
inv_router = APIRouter(prefix="/api/inventory", tags=["inventory"])

STORE_WRITE = require_departments(DepartmentCode.STORE)


# ---- Material catalog: readable by ALL authenticated departments (Planning
# needs availability visibility per spec section 11); writes are STORE-only
# (+ manager/sub-admin via require_departments' built-in cross-dept allow). ----

@router.get("", response_model=list[MaterialOut])
def list_materials(active_only: bool = True, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Material)
    if active_only:
        q = q.filter(Material.is_active == True)  # noqa: E712
    return q.order_by(Material.name).all()


@router.get("/{material_id}", response_model=MaterialOut)
def get_material(material_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    m = db.query(Material).filter(Material.id == material_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Material not found")
    return m


@router.post("", response_model=MaterialOut, status_code=201)
def create_material(payload: MaterialCreate, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    if db.query(Material).filter(Material.sku == payload.sku).first():
        raise HTTPException(status_code=409, detail="A material with this SKU already exists")
    data = payload.model_dump(exclude={"opening_stock"})
    material = Material(**data, current_stock=Decimal("0"), created_by=user.id, updated_by=user.id)
    db.add(material)
    db.flush()
    if payload.opening_stock and payload.opening_stock > 0:
        apply_stock_transaction(
            db, material_id=material.id, txn_type=TxnType.OPENING,
            quantity=payload.opening_stock, user=user, remarks="Opening stock at creation",
        )
    else:
        audit_service.record(db, user=user, action="MATERIAL_CREATED", entity_type="Material", entity_id=material.id)
        db.commit()
    db.refresh(material)
    return material


@router.put("/{material_id}", response_model=MaterialOut)
def update_material(material_id: uuid.UUID, payload: MaterialUpdate, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    material = db.query(Material).filter(Material.id == material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    before = {"minimum_stock": str(material.minimum_stock), "purchase_price": str(material.purchase_price)}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(material, field, value)
    material.updated_by = user.id
    audit_service.record(db, user=user, action="MATERIAL_UPDATED", entity_type="Material", entity_id=material.id,
                          before=before, after=payload.model_dump(exclude_unset=True, mode="json"))
    db.commit()
    db.refresh(material)
    return material


# ---------------- Inventory ledger + stock movement endpoints ----------------
# STORE department writes stock; STORE + MANAGER + SUB_ADMIN can read the
# detailed transaction ledger (other departments only see the material's
# current_stock headline number via /api/materials above, not the ledger).

@inv_router.get("/transactions", response_model=list[InventoryTxnOut])
def list_transactions(material_id: uuid.UUID | None = None, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    q = db.query(InventoryTransaction)
    if material_id:
        q = q.filter(InventoryTransaction.material_id == material_id)
    return q.order_by(InventoryTransaction.created_at.desc()).limit(500).all()


async def _notify_stock(material: Material, txn: InventoryTransaction):
    await manager.broadcast(
        "STOCK_UPDATED",
        {"material_id": str(material.id), "sku": material.sku, "name": material.name,
         "current_stock": str(material.current_stock), "txn_type": txn.txn_type.value},
        visible_to_departments={DepartmentCode.STORE.value, DepartmentCode.PLANNING.value},
    )
    if material.current_stock <= material.reorder_level:
        await manager.broadcast(
            "LOW_STOCK",
            {"material_id": str(material.id), "name": material.name, "current_stock": str(material.current_stock),
             "reorder_level": str(material.reorder_level)},
            visible_to_departments={DepartmentCode.STORE.value},
        )


@inv_router.post("/receive", response_model=InventoryTxnOut, status_code=201)
async def receive_stock(payload: StockTxnRequest, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    txn = apply_stock_transaction(
        db, material_id=payload.material_id, txn_type=TxnType.PURCHASE_RECEIPT, quantity=payload.quantity,
        user=user, unit_price=payload.unit_price, remarks=payload.remarks,
        idempotency_key=payload.idempotency_key, reference_type=payload.reference_type, reference_id=payload.reference_id,
    )
    material = db.query(Material).get(payload.material_id)
    await _notify_stock(material, txn)
    return txn


@inv_router.post("/issue", response_model=InventoryTxnOut, status_code=201)
async def issue_stock(payload: StockTxnRequest, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    try:
        txn = apply_stock_transaction(
            db, material_id=payload.material_id, txn_type=TxnType.ISSUE, quantity=payload.quantity,
            user=user, remarks=payload.remarks, idempotency_key=payload.idempotency_key,
            reference_type=payload.reference_type, reference_id=payload.reference_id,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    material = db.query(Material).get(payload.material_id)
    await _notify_stock(material, txn)
    return txn


@inv_router.post("/adjust", response_model=InventoryTxnOut, status_code=201)
async def adjust_stock(payload: StockTxnRequest, is_increase: bool = True, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    txn_type = TxnType.ADJUSTMENT if is_increase else TxnType.DAMAGE
    try:
        txn = apply_stock_transaction(
            db, material_id=payload.material_id, txn_type=txn_type, quantity=payload.quantity,
            user=user, remarks=payload.remarks, idempotency_key=payload.idempotency_key,
        )
    except InsufficientStockError as e:
        raise HTTPException(status_code=400, detail=str(e))
    material = db.query(Material).get(payload.material_id)
    await _notify_stock(material, txn)
    return txn


@inv_router.post("/return", response_model=InventoryTxnOut, status_code=201)
async def return_stock(payload: StockTxnRequest, user: User = Depends(STORE_WRITE), db: Session = Depends(get_db)):
    txn = apply_stock_transaction(
        db, material_id=payload.material_id, txn_type=TxnType.RETURN, quantity=payload.quantity,
        user=user, remarks=payload.remarks, idempotency_key=payload.idempotency_key,
    )
    material = db.query(Material).get(payload.material_id)
    await _notify_stock(material, txn)
    return txn
