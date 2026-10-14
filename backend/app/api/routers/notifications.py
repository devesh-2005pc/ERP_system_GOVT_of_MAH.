import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.auth.deps import get_current_user
from app.models.system import Notification
from app.models.user import User

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    event_type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


@router.get("", response_model=list[NotificationOut])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A user sees notifications addressed to them personally, or to their
    own department — never another department's notifications."""
    q = db.query(Notification).filter(
        or_(Notification.user_id == user.id, Notification.department_id == user.department_id)
    )
    return q.order_by(Notification.created_at.desc()).limit(100).all()


@router.post("/{notification_id}/read")
def mark_read(notification_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.query(Notification).filter(Notification.id == notification_id).first()
    if not n or (n.user_id != user.id and n.department_id != user.department_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    n.is_read = True
    db.commit()
    return {"ok": True}
