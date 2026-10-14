"""
Inventory transaction service.

CRITICAL REQUIREMENT: concurrent stock operations must never corrupt stock.
The client NEVER sends a resulting stock number — only a delta (issue X,
receive Y, adjust by Z) — and the server computes+writes the new balance
inside a single database transaction with the material row locked
(`SELECT ... FOR UPDATE` on PostgreSQL) so two simultaneous requests against
the same material serialize instead of racing.

On SQLite (dev/test only) `SELECT ... FOR UPDATE` isn't supported; SQLAlchemy
silently ignores `with_for_update()` there, but SQLite's single-writer file
lock still serializes the actual commits, so correctness holds for tests.
PostgreSQL is required for real multi-workstation deployment specifically
because it gives us real row-level locking under concurrent load.
"""
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.material import Material, InventoryTransaction
from app.models.enums import TxnType
from app.models.user import User
from app.services import audit as audit_service


class InsufficientStockError(Exception):
    pass


def apply_stock_transaction(
    db: Session,
    *,
    material_id,
    txn_type: TxnType,
    quantity: Decimal,
    user: User,
    unit_price: Decimal | None = None,
    reference_type: str | None = None,
    reference_id=None,
    remarks: str | None = None,
    idempotency_key: str | None = None,
) -> InventoryTransaction:
    """
    quantity is UNSIGNED and always positive in the request; the sign applied
    to the ledger is derived from txn_type. Returns the created
    InventoryTransaction. Raises InsufficientStockError if an outward
    movement would take stock negative. Commits the transaction itself
    (single atomic unit: lock -> validate -> update -> ledger row -> commit).
    """
    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    # Idempotency: if this exact operation was already applied (e.g. a
    # client retry after a network blip), return the existing result instead
    # of double-applying it.
    if idempotency_key:
        existing = db.query(InventoryTransaction).filter(
            InventoryTransaction.idempotency_key == idempotency_key
        ).first()
        if existing:
            return existing

    outward = txn_type in (TxnType.ISSUE, TxnType.DAMAGE, TxnType.TRANSFER_OUT)
    signed_qty = -quantity if outward else quantity

    try:
        # Row lock: on PostgreSQL this blocks any other concurrent
        # transaction touching the same material row until we commit,
        # making the read-modify-write below atomic across processes.
        material = (
            db.query(Material)
            .filter(Material.id == material_id, Material.is_active == True)  # noqa: E712
            .with_for_update()
            .first()
        )
        if not material:
            raise HTTPException(status_code=404, detail="Material not found")

        new_balance = Decimal(material.current_stock) + signed_qty
        if new_balance < 0:
            raise InsufficientStockError(
                f"Insufficient stock for {material.name}: have {material.current_stock}, "
                f"requested to remove {quantity}"
            )

        before_stock = material.current_stock
        material.current_stock = new_balance
        material.version += 1

        txn = InventoryTransaction(
            material_id=material.id,
            txn_type=txn_type,
            quantity=signed_qty,
            balance_after=new_balance,
            unit_price=unit_price,
            reference_type=reference_type,
            reference_id=reference_id,
            remarks=remarks,
            idempotency_key=idempotency_key,
            created_by=user.id,
        )
        db.add(txn)

        audit_service.record(
            db,
            user=user,
            action=f"STOCK_{txn_type.value}",
            entity_type="Material",
            entity_id=material.id,
            before={"current_stock": str(before_stock)},
            after={"current_stock": str(new_balance)},
            detail=remarks,
        )

        db.commit()
        db.refresh(txn)
        return txn
    except InsufficientStockError:
        db.rollback()
        raise
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent update conflict, please retry")
    except Exception:
        db.rollback()
        raise
