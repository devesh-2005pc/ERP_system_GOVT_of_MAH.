import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class MaterialCreate(BaseModel):
    sku: str
    name: str
    category_id: Optional[uuid.UUID] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None
    gsm: Optional[str] = None
    thickness: Optional[str] = None
    color: Optional[str] = None
    unit: str = "PCS"
    pack_size: Optional[int] = None
    minimum_stock: Decimal = Decimal("0")
    maximum_stock: Optional[Decimal] = None
    reorder_level: Decimal = Decimal("0")
    reorder_quantity: Optional[Decimal] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    purchase_price: Optional[Decimal] = None
    storage_location: Optional[str] = None
    opening_stock: Decimal = Decimal("0")


class MaterialUpdate(BaseModel):
    name: Optional[str] = None
    subcategory: Optional[str] = None
    description: Optional[str] = None
    size: Optional[str] = None
    gsm: Optional[str] = None
    thickness: Optional[str] = None
    color: Optional[str] = None
    unit: Optional[str] = None
    pack_size: Optional[int] = None
    minimum_stock: Optional[Decimal] = None
    maximum_stock: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None
    reorder_quantity: Optional[Decimal] = None
    preferred_supplier_id: Optional[uuid.UUID] = None
    purchase_price: Optional[Decimal] = None
    storage_location: Optional[str] = None
    is_active: Optional[bool] = None


class MaterialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sku: str
    name: str
    unit: str
    current_stock: Decimal
    minimum_stock: Decimal
    reorder_level: Decimal
    purchase_price: Optional[Decimal] = None
    storage_location: Optional[str] = None
    is_active: bool


class StockTxnRequest(BaseModel):
    material_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    unit_price: Optional[Decimal] = None
    remarks: Optional[str] = None
    idempotency_key: Optional[str] = None
    reference_type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None


class InventoryTxnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    material_id: uuid.UUID
    txn_type: str
    quantity: Decimal
    balance_after: Decimal
    unit_price: Optional[Decimal] = None
    remarks: Optional[str] = None
    created_at: datetime
