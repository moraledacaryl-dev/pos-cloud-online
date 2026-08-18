from __future__ import annotations

import json
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.models.entities import AuditLog


AUDIT_PAGE_SIZE_DEFAULT = 50
AUDIT_PAGE_SIZE_MAX = 100


def _entity_links(entity_type: str | None, entity_id: str | None, details: dict | list | None = None) -> dict:
    details = details if isinstance(details, dict) else {}
    order_id = details.get('order_id') or (entity_id if entity_type in {'order', 'pos_order'} else None)
    session_id = details.get('session_id') or (entity_id if entity_type in {'session', 'register_session'} else None)
    refund_id = details.get('refund_id') or (entity_id if entity_type == 'refund' else None)
    room_charge_id = details.get('room_charge_posting_id') or (entity_id if entity_type in {'room_charge', 'room_charge_posting'} else None)
    links = {}
    if order_id:
        links['order'] = f'/orders?order_id={order_id}'
    if session_id:
        links['session'] = f'/sessions?session_id={session_id}'
    if refund_id:
        links['refund'] = f'/orders?refund_id={refund_id}'
    if room_charge_id:
        links['room_charge'] = f'/room-charges?posting_id={room_charge_id}'
    return links


def write_audit_log(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | int | None = None,
    actor_user_id: int | None = None,
    actor_username: str | None = None,
    request_path: str | None = None,
    request_method: str | None = None,
    ip_address: str | None = None,
    status_code: int | None = None,
    details: dict | list | None = None,
    commit: bool = True,
):
    row = AuditLog(actor_user_id=actor_user_id, actor_username=actor_username, action=action, entity_type=entity_type, entity_id=str(entity_id) if entity_id is not None else None, request_path=request_path, request_method=request_method, ip_address=ip_address, status_code=status_code, details_json=json.dumps(details or {}, ensure_ascii=False))
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    else:
        db.flush()
    return row


def _serialize(row: AuditLog) -> dict:
    details = {}
    try:
        details = json.loads(row.details_json or '{}')
    except Exception:
        details = {}
    return {
        'id': row.id,
        'actor_user_id': row.actor_user_id,
        'actor_username': row.actor_username or (row.actor.username if row.actor else None),
        'actor_name': row.actor.full_name if row.actor and row.actor.full_name else (row.actor.username if row.actor else row.actor_username),
        'action': row.action,
        'entity_type': row.entity_type,
        'entity_id': row.entity_id,
        'request_path': row.request_path,
        'request_method': row.request_method,
        'ip_address': row.ip_address,
        'status_code': row.status_code,
        'details': details,
        'links': _entity_links(row.entity_type, row.entity_id, details),
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }


def list_audit_logs(
    db: Session,
    *,
    actor_user_id: int | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    q: str | None = None,
    limit: int = AUDIT_PAGE_SIZE_DEFAULT,
    before_id: int | None = None,
):
    page_size = max(1, min(int(limit or AUDIT_PAGE_SIZE_DEFAULT), AUDIT_PAGE_SIZE_MAX))
    query = db.query(AuditLog).options(selectinload(AuditLog.actor)).order_by(AuditLog.id.desc())
    if before_id is not None:
        query = query.filter(AuditLog.id < int(before_id))
    if actor_user_id:
        query = query.filter(AuditLog.actor_user_id == int(actor_user_id))
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == str(entity_id))
    if date_from:
        query = query.filter(func.date(AuditLog.created_at) >= date_from)
    if date_to:
        query = query.filter(func.date(AuditLog.created_at) <= date_to)
    if q:
        like = f'%{q.strip()}%'
        query = query.filter(or_(AuditLog.actor_username.ilike(like), AuditLog.action.ilike(like), AuditLog.entity_type.ilike(like), AuditLog.entity_id.ilike(like), AuditLog.details_json.ilike(like)))

    rows = query.limit(page_size + 1).all()
    has_more = len(rows) > page_size
    page_rows = rows[:page_size]
    next_cursor = page_rows[-1].id if has_more and page_rows else None
    return {
        'items': [_serialize(row) for row in page_rows],
        'next_cursor': next_cursor,
        'page_size': page_size,
    }
