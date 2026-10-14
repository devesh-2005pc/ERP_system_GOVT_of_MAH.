from sqlalchemy import Column, String, Numeric, ForeignKey, Enum as SAEnum, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.base import IDMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, GUID
from app.models.enums import PurchaseOrderStatus


class Supplier(Base, IDMixin, TimestampMixin, AuditMixin, SoftDeleteMixin):
    """Visible to STORE + ACCOUNTS + MANAGER/SUB_ADMIN (both departments need
    supplier data for purchasing/payment); not visible to Planning/Dispatch/
    Employee departments."""
    __tablename__ = "suppliers"

    name = Column(String(200), nullable=False)
    contact_person = Column(String(150), nullable=True)
    phone = Column(String(30), nullable=True)
    email = Column(String(150), nullable=True)
    address = Column(String(300), nullable=True)
    gst_number = Column(String(30), nullable=True)


class PurchaseOrder(Base, IDMixin, TimestampMixin, AuditMixin):
    """STORE + ACCOUNTS + MANAGER/SUB_ADMIN only."""
    __tablename__ = "purchase_orders"

    po_number = Column(String(30), unique=True, nullable=False)
    supplier_id = Column(GUID(), ForeignKey("suppliers.id"), nullable=False)
    status = Column(SAEnum(PurchaseOrderStatus), nullable=False, default=PurchaseOrderStatus.DRAFT)
    order_date = Column(DateTime, nullable=True)
    expected_date = Column(DateTime, nullable=True)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    linked_request_id = Column(GUID(), ForeignKey("material_requests.id"), nullable=True)

    items = relationship("PurchaseOrderItem", back_populates="po", cascade="all, delete-orphan")
    supplier = relationship("Supplier")


class PurchaseOrderItem(Base, IDMixin):
    __tablename__ = "purchase_order_items"

    po_id = Column(GUID(), ForeignKey("purchase_orders.id"), nullable=False)
    material_id = Column(GUID(), ForeignKey("materials.id"), nullable=False)
    quantity_ordered = Column(Numeric(14, 3), nullable=False)
    quantity_received = Column(Numeric(14, 3), nullable=False, default=0)
    unit_price = Column(Numeric(14, 2), nullable=False)

    po = relationship("PurchaseOrder", back_populates="items")
    material = relationship("Material")


class GoodsReceipt(Base, IDMixin, TimestampMixin, AuditMixin):
    __tablename__ = "goods_receipts"

    po_id = Column(GUID(), ForeignKey("purchase_orders.id"), nullable=False)
    material_id = Column(GUID(), ForeignKey("materials.id"), nullable=False)
    quantity_received = Column(Numeric(14, 3), nullable=False)
    unit_price = Column(Numeric(14, 2), nullable=False)
    remarks = Column(String(300), nullable=True)
    inventory_transaction_id = Column(GUID(), ForeignKey("inventory_transactions.id"), nullable=True)
