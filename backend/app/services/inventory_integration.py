from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

import httpx
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.settings import settings
from app.models.entities import SyncOutboxEvent
from app.services.pos_service import create_outbox_event

INVENTORY_EVENT_TYPES = {
    'sale_completed': 'inventory.sale_completed',
    'sale_voided': 'inventory.sale_voided',
    'sale_refunded': 'inventory.sale_refunded',
    'sale_returned': 'inventory.sale_returned',
}


def _now_text() -> str:
    return datetime.now(UTC).replace(tzinfo=None).replace(microsecond=0).isoformat()


def _join(base: str, path: str) -> str:
    return base.rstrip('/') + '/' + path.lstrip('/')


def should_reverse_inventory_for_void(order_before_void: dict) -> bool:
    return str(order_before_void.get('status') or '').strip().lower() in {'paid', 'folio_pending'}


def should_reverse_inventory_for_refund(order_after_refund: dict) -> bool:
    """Financial refunds never imply a physical stock return.

    A future quantity-aware return/disposition event must explicitly authorize any
    stock restoration. This prevents prepared/served food from recreating consumed
    recipe ingredients merely because the customer received a refund.
    """
    return False


def _valid_inventory_quantity(value, *, item_name: str) -> float:
    """Prevent NaN, negative, zero or rounded-away stock quantities."""
    try:
        quantity = Decimal(str(value))
        if not quantity.is_finite() or quantity <= 0:
            raise ValueError
        quantity = quantity.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        if quantity <= 0:
            raise ValueError
    except (InvalidOperation, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f'Inventory quantity for {item_name} must be positive and finite.') from exc
    return float(quantity)


def build_inventory_event(order: dict, event_type: str, *, return_lines: list[dict] | None = None, return_id: str | None = None) -> dict:
    if event_type not in INVENTORY_EVENT_TYPES:
        raise ValueError(f'Unsupported Inventory event type: {event_type}')
    order_uuid = str(order.get('order_uuid') or '').strip()
    if not order_uuid:
        raise ValueError('Order UUID is required for Inventory handoff.')

    lines = []
    unmapped_lines = []
    source_lines = return_lines if event_type == 'sale_returned' else (order.get('lines') or [])
    for line in source_lines:
        external_product_id = str(line.get('external_product_id') or line.get('sku_code') or line.get('external_sku_id') or '').strip()
        quantity = _valid_inventory_quantity(
            line.get('quantity'),
            item_name=str(line.get('item_name_snapshot') or line.get('item_name') or external_product_id or 'unknown item'),
        )
        if not external_product_id:
            unmapped_lines.append({
                'catalog_item_id': line.get('catalog_item_id'),
                'item_name': line.get('item_name_snapshot'),
                'quantity': quantity,
            })
            continue
        event_line = {'external_product_id': external_product_id, 'quantity': quantity}
        if event_type == 'sale_returned':
            disposition = str(line.get('inventory_disposition') or '').strip().lower()
            if disposition not in {'restore_stock', 'waste'}:
                raise ValueError('Returned Inventory lines require restore_stock or waste disposition.')
            event_line['inventory_disposition'] = disposition
        lines.append(event_line)

    if event_type == 'sale_returned' and not return_id:
        raise ValueError('Physical returns require a unique refund identifier.')
    if event_type == 'sale_returned' and not lines:
        raise ValueError('Physical returns require at least one mapped returned item.')
    return {
        'external_event_id': f'pos:{order_uuid}:{event_type}:{return_id}' if return_id else f'pos:{order_uuid}:{event_type}',
        'external_sale_id': order_uuid,
        'pos_system': 'hidden-oasis-pos',
        'event_type': event_type,
        'lines': lines,
        '_unmapped_lines': unmapped_lines,
        '_order_no': order.get('order_no'),
    }


def enqueue_inventory_event(db: Session, order: dict, event_type: str, *, return_lines: list[dict] | None = None, return_id: str | None = None, commit: bool = True) -> SyncOutboxEvent:
    payload = build_inventory_event(order, event_type, return_lines=return_lines, return_id=return_id)
    if event_type == 'sale_voided':
        # A catalog's SKU code can change after the sale. Reverse the immutable
        # product IDs and quantities from the original sale outbox, not the live
        # catalog or a reserialized order.
        original = db.query(SyncOutboxEvent).filter(
            SyncOutboxEvent.idempotency_key == f"inventory:pos:{payload['external_sale_id']}:sale_completed",
        ).first()
        if original is not None:
            try:
                original_payload = json.loads(original.payload_json or '{}')
            except (TypeError, ValueError) as exc:
                raise ValueError('Original Inventory sale payload is invalid; automatic void reversal is unsafe.') from exc
            if original_payload.get('external_sale_id') != payload['external_sale_id'] or not isinstance(original_payload.get('lines'), list):
                raise ValueError('Original Inventory sale mapping is invalid; automatic void reversal is unsafe.')
            payload['lines'] = original_payload['lines']
            payload['_unmapped_lines'] = original_payload.get('_unmapped_lines') or []
    row = create_outbox_event(
        db,
        aggregate_type='order',
        aggregate_id=int(order['id']),
        event_type=INVENTORY_EVENT_TYPES[event_type],
        payload=payload,
        idempotency_key=f"inventory:{payload['external_event_id']}",
    )
    # Only a newly created (or legacy generic pending) row may be moved into
    # the Inventory queue. Preserve retries, their backoff clock, blocked and
    # suppressed decisions, and acknowledged rows on duplicate enqueue calls.
    if row.status in {'pending', 'failed'}:
        row.status = 'inventory_pending'
        row.last_error = None
        db.add(row)
        if commit:
            db.commit()
        else:
            db.flush()
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


def _mark_suppressed(db: Session, row: SyncOutboxEvent) -> None:
    row.status = 'suppressed'
    row.last_error = 'Inventory integration is not enabled; no delivery was attempted.'
    row.next_retry_at = None
    db.add(row)
    db.commit()


async def run_inventory_outbox_sync(db: Session, limit: int = 25, *, event_id: int | None = None) -> dict:
    now_text = _now_text()
    query = (
        db.query(SyncOutboxEvent)
        .filter(SyncOutboxEvent.event_type.in_(list(INVENTORY_EVENT_TYPES.values())))
        .filter(SyncOutboxEvent.status.in_(['inventory_pending', 'inventory_retry', 'pending', 'suppressed']))
    )
    if event_id is not None:
        query = query.filter(SyncOutboxEvent.id == int(event_id))
    elif settings.inventory_integration_enabled:
        # Apply retry eligibility before LIMIT so old deferred retries cannot
        # starve due inventory sales. When disabled, still suppress queued rows.
        query = query.filter(or_(
            SyncOutboxEvent.next_retry_at.is_(None),
            SyncOutboxEvent.next_retry_at <= now_text,
        ))
    rows = query.order_by(SyncOutboxEvent.id.asc()).limit(max(1, min(int(limit or 25), 500))).all()

    processed = synced = retried = blocked = skipped = 0
    for row in rows:
        if not settings.inventory_integration_enabled:
            if row.status != 'suppressed':
                _mark_suppressed(db, row)
            skipped += 1
            continue
        if row.next_retry_at and row.next_retry_at > now_text:
            skipped += 1
            continue
        if row.event_type in {
            INVENTORY_EVENT_TYPES['sale_voided'],
            INVENTORY_EVENT_TYPES['sale_refunded'],
            INVENTORY_EVENT_TYPES['sale_returned'],
        }:
            # Stock reversals must not overtake a delayed or retried sale.
            # Legacy orders without a sale event retain their existing path.
            original = db.query(SyncOutboxEvent).filter(
                SyncOutboxEvent.aggregate_type == 'order',
                SyncOutboxEvent.aggregate_id == row.aggregate_id,
                SyncOutboxEvent.event_type == INVENTORY_EVENT_TYPES['sale_completed'],
                SyncOutboxEvent.id < row.id,
            ).order_by(SyncOutboxEvent.id.asc()).populate_existing().first()
            if original is not None and original.status != 'synced':
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
            async with httpx.AsyncClient(
                timeout=settings.http_timeout_seconds,
                headers={'Accept': 'application/json', 'X-Integration-Token': token},
                follow_redirects=True,
            ) as client:
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
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            _mark_retry(db, row, f'Inventory HTTP {response.status_code}: {detail}')
            retried += 1
        else:
            _mark_blocked(db, row, f'Inventory rejected event with HTTP {response.status_code}: {detail}')
            blocked += 1

    return {
        'ok': blocked == 0,
        'processed': processed,
        'synced': synced,
        'failed': retried,
        'retrying': retried,
        'blocked': blocked,
        'skipped': skipped,
    }
