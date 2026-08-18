from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions, require_permissions
from app.db.database import get_db
from app.models.customer_display import CustomerDisplayDevice
from app.services.customer_display_security import (
    SNAPSHOT_TTL_SECONDS,
    activate_pairing_code,
    create_pairing_code,
    require_display_device,
    revoke_device,
)
from app.services.pos_service import save_setting_json, setting_json

router = APIRouter()
CHANNEL_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,40}$')


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _channel(value: str) -> str:
    channel = (value or '').strip()
    if not CHANNEL_PATTERN.fullmatch(channel):
        raise HTTPException(status_code=400, detail='Display channel must use letters, numbers, dash, or underscore.')
    return channel


def _snapshot_key(channel: str) -> str:
    return f'customer_display_snapshot:{_channel(channel)}'


def _clean_text(value, max_length: int) -> str:
    return str(value or '').strip()[:max_length]


def _number(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sanitize_snapshot(payload: dict | None) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get('cart') if isinstance(payload.get('cart'), list) else []
    cart = []
    for row in rows[:80]:
        row = row if isinstance(row, dict) else {}
        cart.append({
            'name': _clean_text(row.get('name'), 180),
            'quantity': _number(row.get('quantity')),
            'total': _number(row.get('total')),
        })
    totals = payload.get('totals') if isinstance(payload.get('totals'), dict) else {}
    return {
        'updated_at': _clean_text(payload.get('updated_at'), 50),
        'order_no': _clean_text(payload.get('order_no'), 120),
        'table_label': _clean_text(payload.get('table_label'), 80),
        'cart': cart,
        'totals': {
            'gross': _number(totals.get('gross')),
            'discount': _number(totals.get('discount')),
            'total': _number(totals.get('total')),
        },
    }


def _empty_snapshot() -> dict:
    return {'updated_at': '', 'order_no': '', 'table_label': '', 'cart': [], 'totals': {'gross': 0.0, 'discount': 0.0, 'total': 0.0}}


def _stored_snapshot(db: Session, channel: str) -> dict:
    stored = setting_json(db, _snapshot_key(channel), default={})
    if not isinstance(stored, dict):
        return _empty_snapshot()
    expires_at = stored.get('_expires_at')
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= _now():
                return _empty_snapshot()
        except Exception:
            return _empty_snapshot()
    return _sanitize_snapshot(stored.get('snapshot'))


@router.post('/pairing-code')
def new_pairing_code(
    payload: dict,
    user=Depends(require_permissions('approvals.manage')),
):
    channel = _channel(payload.get('channel') or 'main')
    register_id = payload.get('register_id')
    if register_id is not None:
        try:
            register_id = int(register_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail='register_id must be numeric') from exc
    return create_pairing_code(channel=channel, register_id=register_id, requester_user_id=int(user.id))


@router.post('/activate')
def activate(payload: dict, request: Request, response: Response, db: Session = Depends(get_db)):
    device = activate_pairing_code(db, request, response, str(payload.get('pairing_code') or ''))
    return {'ok': True, 'device_uuid': device.device_uuid, 'channel': device.channel, 'register_id': device.register_id}


@router.get('/devices')
def list_devices(db: Session = Depends(get_db), user=Depends(require_permissions('approvals.manage'))):
    rows = db.query(CustomerDisplayDevice).order_by(CustomerDisplayDevice.created_at.desc()).limit(100).all()
    return [{
        'device_uuid': row.device_uuid,
        'channel': row.channel,
        'register_id': row.register_id,
        'is_active': bool(row.is_active),
        'expires_at': row.expires_at,
        'last_seen_at': row.last_seen_at,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'revoked_at': row.revoked_at,
    } for row in rows]


@router.post('/devices/{device_uuid}/revoke')
def revoke(device_uuid: str, db: Session = Depends(get_db), user=Depends(require_permissions('approvals.manage'))):
    device = db.query(CustomerDisplayDevice).filter(CustomerDisplayDevice.device_uuid == device_uuid).first()
    if not device:
        raise HTTPException(status_code=404, detail='Customer display device not found')
    revoke_device(db, device)
    return {'ok': True, 'device_uuid': device.device_uuid}


@router.get('/{channel}')
def get_snapshot(channel: str, request: Request, response: Response, db: Session = Depends(get_db)):
    normalized = _channel(channel)
    require_display_device(db, request, normalized)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Pragma'] = 'no-cache'
    return _stored_snapshot(db, normalized)


@router.put('/{channel}')
def update_snapshot(
    channel: str,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_any_permissions('pos.use', 'orders.manage')),
):
    normalized = _channel(channel)
    if payload.get('clear') is True or str(payload.get('status') or '').strip().lower() in {'paid', 'cancelled', 'canceled', 'voided', 'closed', 'reset'}:
        wrapper = {'snapshot': _empty_snapshot(), '_expires_at': (_now() + timedelta(seconds=5)).isoformat()}
    else:
        snapshot = _sanitize_snapshot(payload)
        wrapper = {'snapshot': snapshot, '_expires_at': (_now() + timedelta(seconds=SNAPSHOT_TTL_SECONDS)).isoformat()}
    save_setting_json(db, _snapshot_key(normalized), wrapper, username=getattr(user, 'username', None))
    return {'ok': True, 'channel': normalized, 'updated_at': wrapper['snapshot'].get('updated_at')}


@router.delete('/{channel}')
def clear_snapshot(
    channel: str,
    db: Session = Depends(get_db),
    user=Depends(require_any_permissions('pos.use', 'orders.manage')),
):
    normalized = _channel(channel)
    save_setting_json(db, _snapshot_key(normalized), {'snapshot': _empty_snapshot(), '_expires_at': (_now() + timedelta(seconds=5)).isoformat()}, username=getattr(user, 'username', None))
    return {'ok': True, 'channel': normalized}
