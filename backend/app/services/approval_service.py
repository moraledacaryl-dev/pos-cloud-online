from __future__ import annotations

import json
import uuid
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.entities import ManagerApproval, User
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


def _now_text() -> str:
    from datetime import datetime
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _is_manager_like(db: Session, user: User | None) -> bool:
    if not user or not user.is_active:
        return False
    if str(user.role or '').lower() in {'owner', 'manager', 'admin'}:
        return True
    try:
        permissions = set(get_user_permission_keys(db, user))
    except Exception:
        permissions = set()
    return '*' in permissions or 'orders.void' in permissions or 'users.manage' in permissions or 'settings.manage' in permissions


def _serialize(row: ManagerApproval) -> dict:
    details = {}
    try:
        details = json.loads(row.request_details_json or '{}')
    except Exception:
        details = {}
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
        'request_details': details,
        'requested_at': row.requested_at_text,
        'decided_at': row.decided_at_text,
    }


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
    approval_key = str(approval_type or '').strip().lower() or 'approval'
    requester = db.get(User, int(requested_by_user_id)) if requested_by_user_id else None
    approver = db.get(User, int(approved_by_user_id)) if approved_by_user_id else None
    if not approver and _is_manager_like(db, requester):
        approver = requester
        approved_by_user_id = requester.id
    if approver and not _is_manager_like(db, approver):
        raise ValueError('Approving user must be an owner or manager.')
    status = 'approved' if approver else 'pending'
    row = ManagerApproval(
        approval_uuid=str(uuid.uuid4()),
        approval_type=approval_key,
        entity_type=str(entity_type or '').strip() or 'entity',
        entity_id=str(entity_id) if entity_id is not None else None,
        status=status,
        requested_by_user_id=requested_by_user_id,
        approved_by_user_id=approved_by_user_id,
        requested_reason=requested_reason,
        decision_note=decision_note,
        request_details_json=json.dumps(request_details or {}, ensure_ascii=False),
        requested_at_text=_now_text(),
        decided_at_text=_now_text() if approver else None,
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    row = db.query(ManagerApproval).options(selectinload(ManagerApproval.requested_by), selectinload(ManagerApproval.approved_by)).filter(ManagerApproval.id == row.id).first()
    return _serialize(row)


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
    return [_serialize(row) for row in query.limit(limit).all()]


def approve_manager_approval(db: Session, approval_id: int, approved_by_user_id: int, decision_note: str | None = None):
    row = db.query(ManagerApproval).options(selectinload(ManagerApproval.requested_by), selectinload(ManagerApproval.approved_by)).filter(ManagerApproval.id == approval_id).first()
    if not row:
        raise ValueError('Approval not found')
    if row.status != 'pending':
        raise ValueError('Approval is not pending')
    approver = db.get(User, approved_by_user_id)
    if not approver or not _is_manager_like(db, approver):
        raise ValueError('Approving user must be an owner or manager')
    row.status = 'approved'
    row.approved_by_user_id = approved_by_user_id
    row.decision_note = decision_note
    row.decided_at_text = _now_text()
    db.commit()
    db.refresh(row)
    return _serialize(row)


def reject_manager_approval(db: Session, approval_id: int, approved_by_user_id: int, decision_note: str | None = None):
    row = db.query(ManagerApproval).options(selectinload(ManagerApproval.requested_by), selectinload(ManagerApproval.approved_by)).filter(ManagerApproval.id == approval_id).first()
    if not row:
        raise ValueError('Approval not found')
    if row.status != 'pending':
        raise ValueError('Approval is not pending')
    approver = db.get(User, approved_by_user_id)
    if not approver or not _is_manager_like(db, approver):
        raise ValueError('Approving user must be an owner or manager')
    row.status = 'rejected'
    row.approved_by_user_id = approved_by_user_id
    row.decision_note = decision_note
    row.decided_at_text = _now_text()
    db.commit()
    db.refresh(row)
    return _serialize(row)
