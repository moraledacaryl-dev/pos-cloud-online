from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_any_permissions
from app.db.database import get_db
from app.services.pos_service import save_setting_json, setting_json

router = APIRouter()
CHANNEL_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{1,40}$')


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
    for idx, row in enumerate(rows[:80]):
        row = row if isinstance(row, dict) else {}
        cart.append({
            'local_id': _clean_text(row.get('local_id') or idx, 80),
            'name': _clean_text(row.get('name'), 180),
            'quantity': _number(row.get('quantity')),
            'total': _number(row.get('total')),
            'note': _clean_text(row.get('note'), 500),
        })
    totals = payload.get('totals') if isinstance(payload.get('totals'), dict) else {}
    return {
        'updated_at': _clean_text(payload.get('updated_at'), 50),
        'order_no': _clean_text(payload.get('order_no'), 120),
        'guest_name': _clean_text(payload.get('guest_name'), 180),
        'table_label': _clean_text(payload.get('table_label'), 80),
        'cart': cart,
        'totals': {
            'gross': _number(totals.get('gross')),
            'discount': _number(totals.get('discount')),
            'total': _number(totals.get('total')),
        },
    }


@router.get('/{channel}')
def get_snapshot(channel: str, db: Session = Depends(get_db)):
    return _sanitize_snapshot(setting_json(db, _snapshot_key(channel), default={}))


@router.put('/{channel}')
def update_snapshot(
    channel: str,
    payload: dict,
    db: Session = Depends(get_db),
    user=Depends(require_any_permissions('pos.use', 'orders.manage')),
):
    snapshot = _sanitize_snapshot(payload)
    save_setting_json(db, _snapshot_key(channel), snapshot, username=getattr(user, 'username', None))
    return {'ok': True, 'channel': _channel(channel), 'updated_at': snapshot.get('updated_at')}
