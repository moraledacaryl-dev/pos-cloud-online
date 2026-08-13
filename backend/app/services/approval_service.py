from __future__ import annotations

import contextvars
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, inspect, or_, text
from sqlalchemy.orm import Session, selectinload

from app.models.entities import ManagerApproval, User
from app.services.auth_service import authenticate_user
from app.services.permission_service import get_user_permission_keys

APPROVAL_TYPES = {
    'discount',
    'void',
    'refund',
    'cash_paid_out',
    'cash_adjustment',
    'reopen_session',
    'room_charge_dispute',
    'room_charge_write_off',
}
APPROVAL_TTL_SECONDS = 120

_active_grant: contextvars.ContextVar[dict | None] = contextvars.ContextVar('pos_active_manager_approval_grant', default=None)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _now_text() -> str:
    return _utc_now().replace(microsecond=0).isoformat()


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def canonicalize_protected_payload(payload: dict | list | None) -> str:
    return json.dumps(payload or {}, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def protected_payload_digest(payload: dict | list | None) -> str:
    return hashlib.sha256(canonicalize_protected_payload(payload).encode('utf-8')).hexdigest()


def _request_details(row: ManagerApproval) -> dict:
    try:
        details = json.loads(row.request_details_json or '{}')
        return details if isinstance(details, dict) else {'protected_payload': details}
    except Exception:
        return {}


def _grant_meta(row: ManagerApproval) -> dict:
    details = _request_details(row)
    meta = details.get('_approval_grant') or {}
    return meta if isinstance(meta, dict) else {}


def _has_grant_columns(db: Session) -> bool:
    try:
        columns = {column['name'] for column in inspect(db.get_bind()).get_columns('manager_approvals')}
        return {'payload_digest', 'expires_at_text', 'consumed_at_text'} <= columns
    except Exception:
        return False


def _read_grant_columns(db: Session, row: ManagerApproval) -> dict:
    if not _has_grant_columns(db):
        return {}
    result = db.execute(
        text('SELECT payload_digest, expires_at_text, consumed_at_text FROM manager_approvals WHERE id = :id'),
        {'id': row.id},
    ).mappings().first()
    return dict(result or {})


def _write_grant_columns(db: Session, row_id: int, *, payload_digest: str | None = None, expires_at_text: str | None = None, consumed_at_text: str | None = None) -> None:
    if not _has_grant_columns(db):
        return
    db.execute(
        text(
            'UPDATE manager_approvals '
            'SET payload_digest = :payload_digest, expires_at_text = :expires_at_text, consumed_at_text = :consumed_at_text '
            'WHERE id = :id'
        ),
        {
            'id': row_id,
            'payload_digest': payload_digest,
            'expires_at_text': expires_at_text,
            'consumed_at_text': consumed_at_text,
        },
    )


def user_can_manage_approvals(db: Session, user: User | None) -> bool:
    if not user or not user.is_active:
        return False
    try:
        permissions = set(get_user_permission_keys(db, user))
    except Exception:
        permissions = set()
    return '*' in permissions or 'approvals.manage' in permissions


def _serialize(row: ManagerApproval, db: Session | None = None) -> dict:
    details = _request_details(row)
    meta = _grant_meta(row)
    columns = _read_grant_columns(db, row) if db is not None else {}
    return {
        'id': row.id,
        'approval_uuid': row.approval_uuid,
        'approval_type': row.approval_type,
        'entity_type': row.entity_type,
        'entity_id': row.entity_id,
        'status': row.status,
        'requested_by_user_id': row.requested_by_user_id,
        'requested_by_name': row.requested_by.full_name if row.requested_by and row.requested_by.full_name else (row.requested_by.username if row.requested_by else None),
        'approved_by_user_id': row.approved_by_user_id,
        'approved_by_name': row.approved_by.full_name if row.approved_by and row.approved_by.full_name else (row.approved_by.username if row.approved_by else None),
        'requested_reason': row.requested_reason,
        'decision_note': row.decision_note,
        'request_details': {key: value for key, value in details.items() if key != '_approval_grant'},
        'payload_digest': columns.get('payload_digest') or meta.get('payload_digest'),
        'expires_at': columns.get('expires_at_text') or meta.get('expires_at'),
        'consumed_at': columns.get('consumed_at_text') or meta.get('consumed_at'),
        'requested_at': row.requested_at_text,
        'decided_at': row.decided_at_text,
    }


def _load_row(db: Session, *, approval_id: int | None = None, approval_uuid: str | None = None, for_update: bool = False) -> ManagerApproval | None:
    query = db.query(ManagerApproval).options(selectinload(ManagerApproval.requested_by), selectinload(ManagerApproval.approved_by))
    if approval_id is not None:
        query = query.filter(ManagerApproval.id == int(approval_id))
    if approval_uuid is not None:
        query = query.filter(ManagerApproval.approval_uuid == str(approval_uuid))
    if for_update:
        query = query.with_for_update()
    return query.first()


def request_approval(
    db: Session,
    *,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None,
    requested_by_user_id: int,
    requested_reason: str | None,
    protected_payload: dict | list | None,
    ttl_seconds: int = APPROVAL_TTL_SECONDS,
    commit: bool = True,
) -> dict:
    approval_key = str(approval_type or '').strip().lower()
    if approval_key not in APPROVAL_TYPES:
        raise ValueError('Unsupported manager approval type.')
    requester = db.get(User, int(requested_by_user_id))
    if not requester or not requester.is_active:
        raise ValueError('Approval requester is not active.')
    ttl = max(15, min(int(ttl_seconds or APPROVAL_TTL_SECONDS), 600))
    digest = protected_payload_digest(protected_payload)
    expires_at = (_utc_now() + timedelta(seconds=ttl)).replace(microsecond=0).isoformat()
    details = {
        'protected_payload': protected_payload or {},
        '_approval_grant': {
            'payload_digest': digest,
            'expires_at': expires_at,
            'consumed_at': None,
        },
    }
    row = ManagerApproval(
        approval_uuid=str(uuid.uuid4()),
        approval_type=approval_key,
        entity_type=str(entity_type or '').strip() or 'entity',
        entity_id=str(entity_id) if entity_id is not None else None,
        status='pending',
        requested_by_user_id=requester.id,
        approved_by_user_id=None,
        requested_reason=requested_reason,
        decision_note=None,
        request_details_json=json.dumps(details, ensure_ascii=False, sort_keys=True),
        requested_at_text=_now_text(),
        decided_at_text=None,
    )
    db.add(row)
    db.flush()
    _write_grant_columns(db, row.id, payload_digest=digest, expires_at_text=expires_at, consumed_at_text=None)
    if commit:
        db.commit()
        row = _load_row(db, approval_id=row.id)
    return _serialize(row, db)


def approve_grant(db: Session, approval_id: int, approver: User, decision_note: str | None = None, *, commit: bool = True) -> dict:
    row = _load_row(db, approval_id=approval_id, for_update=True)
    if not row:
        raise ValueError('Approval not found.')
    if row.status != 'pending':
        raise ValueError('Approval is not pending.')
    if not user_can_manage_approvals(db, approver):
        raise ValueError('Approver does not have approvals.manage authority.')
    expires_at = _parse_time(_serialize(row, db).get('expires_at'))
    if expires_at and expires_at <= _utc_now():
        row.status = 'expired'
        db.add(row)
        if commit:
            db.commit()
        raise ValueError('Approval grant has expired.')
    row.status = 'approved'
    row.approved_by_user_id = approver.id
    row.decision_note = decision_note
    row.decided_at_text = _now_text()
    db.add(row)
    if commit:
        db.commit()
        row = _load_row(db, approval_id=row.id)
    else:
        db.flush()
    return _serialize(row, db)


def reject_grant(db: Session, approval_id: int, approver: User, decision_note: str | None = None, *, commit: bool = True) -> dict:
    row = _load_row(db, approval_id=approval_id, for_update=True)
    if not row:
        raise ValueError('Approval not found.')
    if row.status != 'pending':
        raise ValueError('Approval is not pending.')
    if not user_can_manage_approvals(db, approver):
        raise ValueError('Approver does not have approvals.manage authority.')
    row.status = 'rejected'
    row.approved_by_user_id = approver.id
    row.decision_note = decision_note
    row.decided_at_text = _now_text()
    db.add(row)
    if commit:
        db.commit()
        row = _load_row(db, approval_id=row.id)
    else:
        db.flush()
    return _serialize(row, db)


def authorize_approval_with_credentials(
    db: Session,
    *,
    requester: User,
    manager_username: str,
    manager_password: str,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None,
    requested_reason: str | None,
    protected_payload: dict | list | None,
) -> dict:
    approver = authenticate_user(db, manager_username, manager_password)
    if not approver:
        raise ValueError('Manager credentials are invalid.')
    if not user_can_manage_approvals(db, approver):
        raise ValueError('Authenticated approver does not have approvals.manage authority.')
    grant = request_approval(
        db,
        approval_type=approval_type,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_by_user_id=requester.id,
        requested_reason=requested_reason,
        protected_payload=protected_payload,
        commit=False,
    )
    approved = approve_grant(db, grant['id'], approver, decision_note='Authenticated manager override', commit=False)
    db.commit()
    row = _load_row(db, approval_id=approved['id'])
    return _serialize(row, db)


def consume_approval_grant(
    db: Session,
    *,
    approval_uuid: str,
    requester_user_id: int,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None,
    protected_payload: dict | list | None,
) -> dict:
    row = _load_row(db, approval_uuid=approval_uuid, for_update=True)
    if not row:
        raise ValueError('Manager approval grant not found.')
    if row.requested_by_user_id != int(requester_user_id):
        raise ValueError('Manager approval grant belongs to a different requester.')
    if row.approval_type != str(approval_type or '').strip().lower():
        raise ValueError('Manager approval grant is for a different action.')
    if row.entity_type != str(entity_type or '').strip():
        raise ValueError('Manager approval grant is for a different entity type.')
    expected_entity_id = str(entity_id) if entity_id is not None else None
    if row.entity_id != expected_entity_id:
        raise ValueError('Manager approval grant is for a different entity.')
    serialized = _serialize(row, db)
    if serialized.get('payload_digest') != protected_payload_digest(protected_payload):
        raise ValueError('Manager approval grant payload does not match this action.')
    if row.status != 'approved':
        if row.status == 'consumed':
            raise ValueError('Manager approval grant has already been consumed.')
        raise ValueError('Manager approval grant is not approved.')
    expires_at = _parse_time(serialized.get('expires_at'))
    if not expires_at or expires_at <= _utc_now():
        row.status = 'expired'
        db.add(row)
        db.flush()
        raise ValueError('Manager approval grant has expired.')
    approver = db.get(User, int(row.approved_by_user_id or 0))
    if not user_can_manage_approvals(db, approver):
        raise ValueError('Approving manager is inactive or no longer has approvals.manage authority.')

    consumed_at = _now_text()
    result = db.execute(
        text("UPDATE manager_approvals SET status = 'consumed' WHERE id = :id AND status = 'approved'"),
        {'id': row.id},
    )
    if result.rowcount != 1:
        raise ValueError('Manager approval grant was already consumed.')
    details = _request_details(row)
    meta = details.setdefault('_approval_grant', {})
    meta['consumed_at'] = consumed_at
    row.request_details_json = json.dumps(details, ensure_ascii=False, sort_keys=True)
    row.status = 'consumed'
    db.add(row)
    _write_grant_columns(
        db,
        row.id,
        payload_digest=serialized.get('payload_digest'),
        expires_at_text=serialized.get('expires_at'),
        consumed_at_text=consumed_at,
    )
    db.flush()
    return _serialize(row, db)


def set_active_consumed_grant(grant: dict):
    return _active_grant.set(grant)


def reset_active_consumed_grant(token) -> None:
    _active_grant.reset(token)


def active_consumed_grant() -> dict | None:
    return _active_grant.get()


def create_manager_approval(
    db: Session,
    *,
    approval_type: str,
    entity_type: str,
    entity_id: str | int | None = None,
    requested_by_user_id: int | None = None,
    approved_by_user_id: int | None = None,
    requested_reason: str | None = None,
    decision_note: str | None = None,
    request_details: dict | list | None = None,
    commit: bool = True,
):
    """Compatibility bridge for existing POS service calls.

    Protected HTTP routes consume a scoped grant first and set it in context.  The
    legacy POS service then calls this function while building its normal audit
    trail; in that case we return the already-consumed grant instead of creating a
    second approval.  Arbitrary client-supplied approver IDs are never sufficient.
    """
    active = active_consumed_grant()
    if active:
        if active.get('approval_type') != str(approval_type or '').strip().lower():
            raise ValueError('Consumed approval grant does not match this action.')
        return active

    if requested_by_user_id and approved_by_user_id and int(requested_by_user_id) == int(approved_by_user_id):
        requester = db.get(User, int(requested_by_user_id))
        if user_can_manage_approvals(db, requester):
            grant = request_approval(
                db,
                approval_type=approval_type,
                entity_type=entity_type,
                entity_id=entity_id,
                requested_by_user_id=requester.id,
                requested_reason=requested_reason,
                protected_payload=request_details or {},
                commit=False,
            )
            approved = approve_grant(db, grant['id'], requester, decision_note=decision_note or 'Authenticated manager self-action', commit=False)
            consumed = consume_approval_grant(
                db,
                approval_uuid=approved['approval_uuid'],
                requester_user_id=requester.id,
                approval_type=approval_type,
                entity_type=entity_type,
                entity_id=entity_id,
                protected_payload=request_details or {},
            )
            if commit:
                db.commit()
            return consumed

    raise ValueError('A server-verified manager approval grant is required.')


def list_manager_approvals(db: Session, *, approval_id: int | None = None, status: str | None = None, approval_type: str | None = None, entity_type: str | None = None, requested_by_user_id: int | None = None, approved_by_user_id: int | None = None, date_from: str | None = None, date_to: str | None = None, q: str | None = None, limit: int = 200):
    query = db.query(ManagerApproval).options(selectinload(ManagerApproval.requested_by), selectinload(ManagerApproval.approved_by)).order_by(ManagerApproval.id.desc())
    if approval_id:
        query = query.filter(ManagerApproval.id == approval_id)
    if status:
        query = query.filter(ManagerApproval.status == status)
    if approval_type:
        query = query.filter(ManagerApproval.approval_type == approval_type)
    if entity_type:
        query = query.filter(ManagerApproval.entity_type == entity_type)
    if requested_by_user_id:
        query = query.filter(ManagerApproval.requested_by_user_id == int(requested_by_user_id))
    if approved_by_user_id:
        query = query.filter(ManagerApproval.approved_by_user_id == int(approved_by_user_id))
    if date_from:
        query = query.filter(func.date(ManagerApproval.created_at) >= date_from)
    if date_to:
        query = query.filter(func.date(ManagerApproval.created_at) <= date_to)
    if q:
        like = f'%{q.strip()}%'
        query = query.filter(or_(ManagerApproval.entity_id.ilike(like), ManagerApproval.requested_reason.ilike(like), ManagerApproval.decision_note.ilike(like), ManagerApproval.request_details_json.ilike(like)))
    return [_serialize(row, db) for row in query.limit(max(1, min(int(limit or 200), 500))).all()]


def approve_manager_approval(db: Session, approval_id: int, approved_by_user_id: int, decision_note: str | None = None):
    approver = db.get(User, int(approved_by_user_id))
    if not approver:
        raise ValueError('Approving user not found.')
    return approve_grant(db, approval_id, approver, decision_note)


def reject_manager_approval(db: Session, approval_id: int, approved_by_user_id: int, decision_note: str | None = None):
    approver = db.get(User, int(approved_by_user_id))
    if not approver:
        raise ValueError('Approving user not found.')
    return reject_grant(db, approval_id, approver, decision_note)
