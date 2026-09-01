from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.entities import SyncOutboxEvent
from app.services.pos_service import create_outbox_event


INVENTORY_EVENT_TYPES = {
    'sale_completed': 'inventory.sale_completed',
    'sale_voided': 'inventory.sale_voided',
    'sale_refunded': 'inventory.sale_refunded',
}


def _now_text() -> str:
    return datetime.now(UTC).replace(tzinfo=None).replace(microsecond=0).isoformat()


def _join(base: str, path: str) -> str:
    return base.rstrip('/') + '/' + path.lstrip('/')


def should_reverse_inventory_for_void(order_before_void: dict) -> bool:
    return str(order_before_void.get('status') or '').strip().lower() in {'paid', 'folio_pending'}


def should_reverse_inventory_for_refund(order_after_refund: dict) -> bool:
    return str(order_after_refund.get('refund_status') or '').strip().lower() == 'fully_refunded'


def build_inventory_event(order: dict, event_type: str) -> dict:
    if event_type not in INVENTORY_EVENT_TYPES:
        raise ValueError(f'Unsupported Inventory event type: {event_type}')
    order_uuid = str(order.get('order_uuid') or '').strip()
    if not order_uuid:
        raise ValueError('Order UUID is required for Inventory handoff.')

    lines = []
    unmapped_lines = []
    for line in order.get('lines') or []:
        external_product_id = str(line.get('sku_code') or line.get('external_sku_id') or '').strip()
        quantity = float(line.get('quantity') or 0)
        if quantity <= 0:
            continue
        if not external_product_id:
            unmapped_lines.append({
                'catalog_item_id': line.get('catalog_item_id'),
                'item_name': line.get('item_name_snapshot'),
                'quantity': quantity,
            })
            continue
        lines.append({'external_product_id': external_product_id, 'quantity': quantity})

    return {
        'external_event_id': f'pos:{order_uuid}:{event_type}',
        'external_sale_id': order_uuid,
        'pos_system': 'hidden-oasis-pos',
        'event_type': event_type,
        'lines': lines,
        '_unmapped_lines': unmapped_lines,
        '_order_no': order.get('order_no'),
    }


def enqueue_inventory_event(db: Session, order: dict, event_type: str) -> SyncOutboxEvent:
    payload = build_inventory_event(order, event_type)
    row = create_outbox_event(
        db,
        aggregate_type='order',
        aggregate_id=int(order['id']),
        event_type=INVENTORY_EVENT_TYPES[event_type],
        payload=payload,
        idempotency_key=f"inventory:{payload['external_event_id']}",
    )
    if row.status != 'synced':
        row.status = 'inventory_pending'
        row.last_error = None
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _mark_retry(db: Session, row: SyncOutboxEvent, error: str) -> None:
    row.retry_count = int(row.retry_count or 0) + 1
    row.status = 'inventory_retry'
    row.last_error = error[:2000]
    row.next_retry_at = (datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=min(row.retry_count * 2, 30))).replace(microsecond=0).isoformat()
    db.add(row)
    db.commit()


def _mark_blocked(db: Session, row: SyncOutboxEvent, error: str) -> None:
    row.retry_count = int(row.retry_count or 0) + 1
    row.status = 'blocked'
    row.last_error = error[:2000]
    row.next_retry_at = None
    db.add(row)
    db.commit()


async def run_inventory_outbox_sync(db: Session, limit: int = 25) -> dict:
    rows = (
        db.query(SyncOutboxEvent)
        .filter(SyncOutboxEvent.event_type.in_(list(INVENTORY_EVENT_TYPES.values())))
        .filter(SyncOutboxEvent.status.in_(['inventory_pending', 'inventory_retry', 'pending']))
        .order_by(SyncOutboxEvent.id.asc())
        .limit(max(int(limit or 1), 1))
        .all()
    )

    processed = synced = retried = blocked = skipped = 0
    now_text = _now_text()
    for row in rows:
        if row.next_retry_at and row.next_retry_at > now_text:
            skipped += 1
            continue
        processed += 1
        row.last_attempt_at = now_text
        db.add(row)
        db.commit()

        try:
            payload = json.loads(row.payload_json or '{}')
        except Exception:
            _mark_blocked(db, row, 'Inventory event payload is not valid JSON.')
            blocked += 1
            continue

        unmapped = payload.get('_unmapped_lines') or []
        if unmapped:
            names = ', '.join(str(item.get('item_name') or item.get('catalog_item_id') or 'unknown item') for item in unmapped[:5])
            _mark_blocked(db, row, f'Inventory handoff blocked: POS lines are missing Inventory SKU mapping ({names}).')
            blocked += 1
            continue
        if not payload.get('lines'):
            _mark_blocked(db, row, 'Inventory handoff blocked: sale contains no Inventory-mapped lines.')
            blocked += 1
            continue
        if not settings.inventory_integration_enabled:
            _mark_blocked(db, row, 'Inventory integration is disabled in POS configuration.')
            blocked += 1
            continue

        base = (settings.inventory_api_base or '').strip()
        token = (settings.inventory_integration_token or '').strip()
        if not base or not token:
            _mark_blocked(db, row, 'Inventory integration URL or token is not configured.')
            blocked += 1
            continue

        outbound = {
            'external_event_id': payload.get('external_event_id'),
            'external_sale_id': payload.get('external_sale_id'),
            'pos_system': payload.get('pos_system') or 'hidden-oasis-pos',
            'event_type': payload.get('event_type'),
            'lines': payload.get('lines') or [],
        }
        try:
            async with httpx.AsyncClient(timeout=settings.http_timeout_seconds, headers={'Accept': 'application/json', 'X-Integration-Token': token}) as client:
                response = await client.post(_join(base, settings.inventory_pos_events_path), json=outbound)
        except Exception as exc:
            _mark_retry(db, row, f'Inventory network failure: {exc}')
            retried += 1
            continue

        if 200 <= response.status_code < 300:
            row.status = 'synced'
            row.synced_at = _now_text()
            row.next_retry_at = None
            row.last_error = None
            db.add(row)
            db.commit()
            synced += 1
            continue

        detail = response.text[:1200]
        if response.status_code >= 500:
            _mark_retry(db, row, f'Inventory HTTP {response.status_code}: {detail}')
            retried += 1
        else:
            _mark_blocked(db, row, f'Inventory rejected event with HTTP {response.status_code}: {detail}')
            blocked += 1

    return {
        'ok': blocked == 0,
        'processed': processed,
        'synced': synced,
        'retrying': retried,
        'blocked': blocked,
        'skipped': skipped,
    }
