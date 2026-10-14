import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.auth.deps import require_manager
from app.models.system import AuditLog
from app.models.user import User

router = APIRouter(prefix="/api/audit-logs", tags=["audit"])


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    employee_id: Optional[str] = None
    department_code: Optional[str] = None
    action: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    detail: Optional[str] = None


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(200, le=1000),
    user: User = Depends(require_manager),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if action:
        q = q.filter(AuditLog.action == action)
    if entity_type:
        q = q.filter(AuditLog.entity_type == entity_type)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()
