from sqlalchemy import Column, String, Numeric, ForeignKey, Text, Enum as SAEnum, Integer
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, GUID
from app.models.enums import TxnType


class MaterialCategory(Base, IDMixin, TimestampMixin):
    __tablename__ = "material_categories"
    name = Column(String(120), unique=True, nullable=False)
    parent_id = Column(GUID(), ForeignKey("material_categories.id"), nullable=True)


class Material(Base, IDMixin, TimestampMixin, AuditMixin, SoftDeleteMixin):
    """Material master. Owned/edited by STORE (+ MANAGER/SUB_ADMIN). Read
    access is shared across departments because Planning must be able to
    check availability (spec section 11) and any department may need to
    request materials — only the STORE-owned *transactional ledger*
    (InventoryTransaction) and internal stock-management detail are
    department-restricted, not the catalog + current stock headline figure."""
    __tablename__ = "materials"

    sku = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(200), nullable=False)
    category_id = Column(GUID(), ForeignKey("material_categories.id"), nullable=True)
    subcategory = Column(String(120), nullable=True)
    description = Column(Text, nullable=True)

    size = Column(String(50), nullable=True)
    gsm = Column(String(20), nullable=True)
    thickness = Column(String(20), nullable=True)
    color = Column(String(50), nullable=True)
    unit = Column(String(20), nullable=False, default="PCS")  # PCS, SHEET, KG, L, ROLL...
    pack_size = Column(Integer, nullable=True)

    current_stock = Column(Numeric(14, 3), nullable=False, default=0)
    minimum_stock = Column(Numeric(14, 3), nullable=False, default=0)
    maximum_stock = Column(Numeric(14, 3), nullable=True)
    reorder_level = Column(Numeric(14, 3), nullable=False, default=0)
    reorder_quantity = Column(Numeric(14, 3), nullable=True)

    preferred_supplier_id = Column(GUID(), ForeignKey("suppliers.id"), nullable=True)
    purchase_price = Column(Numeric(14, 2), nullable=True)
    storage_location = Column(String(120), nullable=True)

    # Optimistic-concurrency guard in addition to the row-lock used on the
    # hot inventory-update path (defence in depth).
    version = Column(Integer, nullable=False, default=1)

    preferred_supplier = relationship("Supplier", foreign_keys=[preferred_supplier_id])


class InventoryTransaction(Base, IDMixin, TimestampMixin, AuditMixin):
    """Immutable stock ledger. Every stock change is a row here — the
    material's current_stock is a derived cache, never edited directly by a
    client. STORE + MANAGER + SUB_ADMIN only (see rbac dept-scope rules)."""
    __tablename__ = "inventory_transactions"

    material_id = Column(GUID(), ForeignKey("materials.id"), nullable=False, index=True)
    txn_type = Column(SAEnum(TxnType), nullable=False)
    quantity = Column(Numeric(14, 3), nullable=False)  # signed: + for in, - for out
    balance_after = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=True)
    reference_type = Column(String(50), nullable=True)  # e.g. 'MATERIAL_REQUEST', 'GOODS_RECEIPT'
    reference_id = Column(GUID(), nullable=True)
    remarks = Column(String(500), nullable=True)
    idempotency_key = Column(String(100), unique=True, nullable=True)

    material = relationship("Material")
