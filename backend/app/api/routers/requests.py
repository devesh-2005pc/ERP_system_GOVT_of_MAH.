import random
import string
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.auth.deps import get_current_user, is_cross_department
from app.models.enums import RequestStatus, DepartmentCode
from app.models.request import MaterialRequest, MaterialRequestItem, RequestApproval
from app.models.material import Material
from app.models.user import User
from app.schemas.request import MaterialRequestCreate, MaterialRequestOut, ApprovalDecision, FulfillItem
from app.services import audit as audit_service
from app.services.inventory import apply_stock_transaction, InsufficientStockError
from app.models.enums import TxnType
from app.ws.manager import manager

router = APIRouter(prefix="/api/material-requests", tags=["material-requests"])


def _gen_request_no(db: Session) -> str:
    suffix = "".join(random.choices(string.digits, k=6))
    return f"MR-{suffix}"


@router.get("", response_model=list[MaterialRequestOut])
def list_requests(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Requesting department sees its own requests. STORE (fulfiller) sees
    all requests (they must action them). MANAGER/SUB_ADMIN see all."""
    q = db.query(MaterialRequest).options(joinedload(MaterialRequest.items))
    if not is_cross_department(user) and user.department.code != DepartmentCode.STORE:
        q = q.filter(MaterialRequest.requesting_department_id == user.department_id)
    return q.order_by(MaterialRequest.created_at.desc()).all()


@router.post("", response_model=MaterialRequestOut, status_code=201)
def create_request(payload: MaterialRequestCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.items:
        raise HTTPException(status_code=400, detail="At least one item is required")
    for item in payload.items:
        if not db.query(Material).filter(Material.id == item.material_id, Material.is_active == True).first():  # noqa: E712
            raise HTTPException(status_code=404, detail=f"Material {item.material_id} not found")

    req = MaterialRequest(
        request_no=_gen_request_no(db),
        requesting_department_id=user.department_id,
        requested_by=user.id,
        reason=payload.reason,
        priority=payload.priority,
        status=RequestStatus.SUBMITTED,
        created_by=user.id,
    )
    db.add(req)
    db.flush()
    for item in payload.items:
        db.add(MaterialRequestItem(request_id=req.id, material_id=item.material_id, quantity_requested=item.quantity_requested))
    audit_service.record(db, user=user, action="MATERIAL_REQUEST_CREATED", entity_type="MaterialRequest", entity_id=req.id)
    db.commit()
    db.refresh(req)
    return req


def _get_request_for_user(db: Session, request_id: uuid.UUID, user: User) -> MaterialRequest:
    req = db.query(MaterialRequest).options(joinedload(MaterialRequest.items)).filter(MaterialRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    allowed = is_cross_department(user) or user.department.code == DepartmentCode.STORE or req.requesting_department_id == user.department_id
    if not allowed:
        raise HTTPException(status_code=403, detail="Not authorized to view this request")
    return req


@router.get("/{request_id}", response_model=MaterialRequestOut)
def get_request(request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_request_for_user(db, request_id, user)


@router.post("/{request_id}/approve", response_model=MaterialRequestOut)
async def approve_request(request_id: uuid.UUID, payload: ApprovalDecision, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Store reviews availability; Manager/Sub-admin can also approve/reject
    at any stage (per manager's global authority)."""
    req = _get_request_for_user(db, request_id, user)
    if user.department.code not in (DepartmentCode.STORE,) and not is_cross_department(user):
        raise HTTPException(status_code=403, detail="Only Store or Manager/Sub-Admin can approve material requests")
    if req.status not in (RequestStatus.SUBMITTED, RequestStatus.PENDING_APPROVAL):
        raise HTTPException(status_code=400, detail=f"Request is in status {req.status.value}, cannot be approved")

    decision = payload.decision.upper()
    if decision not in ("APPROVED", "REJECTED"):
        raise HTTPException(status_code=400, detail="decision must be APPROVED or REJECTED")

    req.status = RequestStatus.APPROVED if decision == "APPROVED" else RequestStatus.REJECTED
    db.add(RequestApproval(request_id=req.id, approver_id=user.id, decision=decision, comments=payload.comments))
    audit_service.record(db, user=user, action=f"MATERIAL_REQUEST_{decision}", entity_type="MaterialRequest", entity_id=req.id)
    db.commit()
    db.refresh(req)
    from app.models.user import Department
    requesting_dept = db.query(Department).get(req.requesting_department_id)
    await manager.broadcast(
        "REQUEST_APPROVED" if decision == "APPROVED" else "REQUEST_REJECTED",
        {"request_id": str(req.id), "status": req.status.value},
        visible_to_departments={requesting_dept.code.value} if requesting_dept else set(),
    )
    return req


@router.post("/{request_id}/fulfill", response_model=MaterialRequestOut)
async def fulfill_request(request_id: uuid.UUID, items: list[FulfillItem], user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Store issues stock against an approved request. Creates real inventory
    transactions (never just marks the request 'fulfilled' without moving
    real stock)."""
    if user.department.code != DepartmentCode.STORE and not is_cross_department(user):
        raise HTTPException(status_code=403, detail="Only Store can fulfill material requests")
    req = _get_request_for_user(db, request_id, user)
    if req.status not in (RequestStatus.APPROVED, RequestStatus.PARTIALLY_FULFILLED):
        raise HTTPException(status_code=400, detail=f"Request must be APPROVED before fulfillment (current: {req.status.value})")

    by_material = {i.material_id: i for i in req.items}
    for fulfill_item in items:
        line = by_material.get(fulfill_item.material_id)
        if not line:
            raise HTTPException(status_code=400, detail=f"Material {fulfill_item.material_id} is not part of this request")
        remaining = line.quantity_requested - line.quantity_fulfilled
        if fulfill_item.quantity_to_fulfill > remaining:
            raise HTTPException(status_code=400, detail=f"Cannot fulfill more than remaining ({remaining}) for this line")
        try:
            txn = apply_stock_transaction(
                db, material_id=line.material_id, txn_type=TxnType.ISSUE, quantity=fulfill_item.quantity_to_fulfill,
                user=user, reference_type="MATERIAL_REQUEST", reference_id=req.id,
                remarks=f"Issued against request {req.request_no}",
            )
        except InsufficientStockError as e:
            raise HTTPException(status_code=400, detail=str(e))
        line.quantity_fulfilled += fulfill_item.quantity_to_fulfill
        material = db.query(Material).get(line.material_id)
        await manager.broadcast(
            "STOCK_UPDATED",
            {"material_id": str(material.id), "current_stock": str(material.current_stock)},
            visible_to_departments={DepartmentCode.STORE.value, DepartmentCode.PLANNING.value},
        )

    all_full = all(i.quantity_fulfilled >= i.quantity_requested for i in req.items)
    any_full = any(i.quantity_fulfilled > 0 for i in req.items)
    req.status = RequestStatus.FULFILLED if all_full else (RequestStatus.PARTIALLY_FULFILLED if any_full else req.status)
    audit_service.record(db, user=user, action="MATERIAL_REQUEST_FULFILLED", entity_type="MaterialRequest", entity_id=req.id)
    db.commit()
    db.refresh(req)
    from app.models.user import Department
    requesting_dept = db.query(Department).get(req.requesting_department_id)
    await manager.broadcast(
        "REQUEST_APPROVED" if req.status == RequestStatus.FULFILLED else "STOCK_UPDATED",
        {"request_id": str(req.id), "status": req.status.value},
        visible_to_departments={requesting_dept.code.value} if requesting_dept else set(),
    )
    return req


@router.post("/{request_id}/cancel", response_model=MaterialRequestOut)
def cancel_request(request_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    req = _get_request_for_user(db, request_id, user)
    if req.requesting_department_id != user.department_id and not is_cross_department(user):
        raise HTTPException(status_code=403, detail="Only the requesting department can cancel this request")
    if req.status in (RequestStatus.FULFILLED, RequestStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Cannot cancel a finished/cancelled request")
    req.status = RequestStatus.CANCELLED
    audit_service.record(db, user=user, action="MATERIAL_REQUEST_CANCELLED", entity_type="MaterialRequest", entity_id=req.id)
    db.commit()
    db.refresh(req)
    return req
