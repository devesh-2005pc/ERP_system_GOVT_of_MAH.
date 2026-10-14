from sqlalchemy.orm import Session

from app.models.system import AuditLog
from app.models.user import User


def record(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity_type: str | None = None,
    entity_id=None,
    before=None,
    after=None,
    ip_address: str | None = None,
    detail: str | None = None,
):
    log = AuditLog(
        user_id=user.id if user else None,
        employee_id=user.employee_id if user else None,
        department_code=user.department.code.value if user and user.department else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id else None,
        before_state=before,
        after_state=after,
        ip_address=ip_address,
        detail=detail,
    )
    db.add(log)
    # Caller controls the commit boundary (same transaction as the business change).
    return log
