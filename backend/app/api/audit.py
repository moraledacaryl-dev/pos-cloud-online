from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions
from app.db.database import get_db
from app.services.audit_service import list_audit_logs

router = APIRouter()


@router.get('')
def audit_logs(
    actor_user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    before_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user=Depends(require_any_permissions('settings.manage', 'users.manage', 'reports.view', 'audit.view')),
):
    return list_audit_logs(
        db,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        date_from=date_from,
        date_to=date_to,
        q=q,
        limit=limit,
        before_id=before_id,
    )
