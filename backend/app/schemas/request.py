import uuid
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class RequestItemIn(BaseModel):
    material_id: uuid.UUID
    quantity_requested: Decimal


class MaterialRequestCreate(BaseModel):
    reason: Optional[str] = None
    priority: str = "NORMAL"
    items: List[RequestItemIn]


class ApprovalDecision(BaseModel):
    decision: str  # APPROVED / REJECTED
    comments: Optional[str] = None


class FulfillItem(BaseModel):
    material_id: uuid.UUID
    quantity_to_fulfill: Decimal


class RequestItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    material_id: uuid.UUID
    quantity_requested: Decimal
    quantity_fulfilled: Decimal


class MaterialRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    request_no: str
    requesting_department_id: uuid.UUID
    status: str
    priority: str
    reason: Optional[str] = None
    items: List[RequestItemOut] = []
