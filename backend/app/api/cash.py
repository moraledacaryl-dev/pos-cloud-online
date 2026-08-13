import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_permissions
from app.db.database import get_db
from app.models.entities import AuditLog
from app.schemas.common import CashMovementCreate
from app.services.approval_guard import consume_protected_approval, reject_legacy_client_approver
from app.services.payment_control_policy import validate_cash_movement_control
from app.services.pos_service import create_cash_movement, list_cash_movements

router = APIRouter()

SENSITIVE_CASH_MOVEMENTS = {
    'paid_out',
    'safe_drop',
    'bank_deposit',
    'drawer_transfer',
    'owner_withdrawal',
    'adjustment_in',
    'adjustment_out',
    'cash_adjustment',
}


def _approval_type(movement_type: str) -> str:
    return 'cash_paid_out' if movement_type == 'paid_out' else 'cash_adjustment'


def _correct_cash_audit_attribution(db: Session, movement_id: int, current_user, grant: dict) -> None:
    row = db.query(AuditLog).filter(
        AuditLog.action == 'cash_movement.created',
        AuditLog.entity_type == 'cash_movement',
        AuditLog.entity_id == str(movement_id),
    ).order_by(AuditLog.id.desc()).first()
    if not row:
        return
    try:
        details = json.loads(row.details_json or '{}')
    except Exception:
        details = {}
    details.update({
        'approval_grant_uuid': grant.get('approval_uuid'),
        'requested_by_user_id': current_user.id,
        'approved_by_user_id': grant.get('approved_by_user_id'),
        'approval_payload_digest': grant.get('payload_digest'),
    })
    row.actor_user_id = current_user.id
    row.actor_username = current_user.username
    row.details_json = json.dumps(details, ensure_ascii=False, sort_keys=True)
    db.add(row)
    db.commit()


@router.get('/')
def cash_movements(session_id: int | None = None, limit: int = 300, db: Session = Depends(get_db), user=Depends(require_permissions('cash.manage'))):
    return list_cash_movements(db, session_id=session_id, limit=limit)


@router.post('/')
def add_cash_movement(payload: CashMovementCreate, db: Session = Depends(get_db), current_user=Depends(require_permissions('cash.manage'))):
    try:
        reject_legacy_client_approver(payload)
        validate_cash_movement_control(payload)
        movement_type = str(payload.movement_type or '').strip().lower()
        requires_approval = movement_type in SENSITIVE_CASH_MOVEMENTS or bool(payload.requires_approval)
        if not requires_approval:
            return create_cash_movement(db, payload, approved_by_user_id=getattr(current_user, 'id', None))

        with consume_protected_approval(
            db,
            requester=current_user,
            payload=payload,
            approval_type=_approval_type(movement_type),
            entity_type='cash_movement',
            entity_id=None,
            requested_reason=payload.note or payload.category or movement_type,
        ) as grant:
            payload.requires_approval = True
            result = create_cash_movement(db, payload, approved_by_user_id=grant['approved_by_user_id'])
        _correct_cash_audit_attribution(db, int(result['id']), current_user, grant)
        return result
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
