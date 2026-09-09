import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.json_utils import json_dumps
from app.core.settings import settings
from app.models.entities import SyncOutboxEvent

logger = logging.getLogger(__name__)

OPERATIONS_EVENT_TYPES = {
    'daily_sales_context',
    'drawer_variance.alert',
    'room_charge.pending_frontdesk_post',
    'refund.review_needed',
    'void.review_needed',
    'open_orders.warning',
    'unpaid_orders.warning',
    'order.finalized',
    'payment.refunded',
    'order.voided',
    'cash_movement.created',
    'session.closed',
    'room_charge.request_created',
}
OPERATIONS_EVENT_PREFIX = 'operations.v2.'


def _operations_url() -> str:
    base = settings.operations_api_base.rstrip('/')
    suffix = f'/integrations/v2/events/{settings.operations_source_app}'
    if base.endswith(suffix):
        return base
    if base.endswith('/api'):
        return f'{base}{suffix}'
    return f'{base}/api{suffix}'


def _build_envelope(
    event_type: str,
    event_id: str,
    *,
    title: str,
    summary: str = '',
    priority: str = 'Normal',
    payload: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: str | int | None = None,
    external_user_id: str | int | None = None,
    occurred_at: datetime | str | None = None,
) -> dict[str, Any]:
    if event_type not in OPERATIONS_EVENT_TYPES:
        raise ValueError(f'Operations v2 does not accept {event_type}')
    if occurred_at is None:
        occurred_at = datetime.now(timezone.utc)
    return {
        'event_id': str(event_id),
        'event_type': event_type,
        'schema_version': 1,
        'occurred_at': occurred_at,
        'priority': priority if priority in {'Low', 'Normal', 'High', 'Critical'} else 'Normal',
        'title': title,
        'summary': summary,
        'payload': payload or {},
        'subject': {
            'type': subject_type,
            'id': str(subject_id) if subject_id is not None else None,
            'external_user_id': str(external_user_id) if external_user_id is not None else None,
        },
    }


def publish_operations_event(
    event_type: str,
    event_id: str,
    *,
    title: str,
    summary: str = '',
    priority: str = 'Normal',
    payload: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: str | int | None = None,
    external_user_id: str | int | None = None,
    occurred_at: datetime | str | None = None,
) -> bool:
    """Attempt an immediate idempotent delivery.

    Business routes use ``enqueue_operations_event`` so a network failure cannot
    lose the event. This direct function remains useful for health probes and
    compatibility callers that do not own a database session.
    """
    envelope = _build_envelope(
        event_type,
        event_id,
        title=title,
        summary=summary,
        priority=priority,
        payload=payload,
        subject_type=subject_type,
        subject_id=subject_id,
        external_user_id=external_user_id,
        occurred_at=occurred_at,
    )
    if not settings.operations_integration_enabled:
        return False
    key = settings.operations_integration_key.strip()
    if not settings.operations_api_base.strip() or not key:
        logger.warning('operations.integration_not_configured', extra={'event_type': event_type})
        return False
    try:
        response = httpx.post(
            _operations_url(),
            headers={'X-Integration-Api-Key': key},
            json=jsonable_encoder(envelope),
            timeout=settings.operations_integration_timeout_seconds,
            follow_redirects=True,
        )
        if not 200 <= response.status_code < 300:
            logger.warning(
                'operations.integration_delivery_failed',
                extra={
                    'event_type': event_type,
                    'event_id': str(event_id),
                    'status_code': response.status_code,
                },
            )
            return False
        return True
    except Exception as exc:
        logger.warning(
            'operations.integration_delivery_failed',
            extra={'event_type': event_type, 'event_id': str(event_id), 'error': str(exc)},
        )
        return False


def enqueue_operations_event(
    db: Session,
    event_type: str,
    event_id: str,
    *,
    title: str,
    summary: str = '',
    priority: str = 'Normal',
    payload: dict[str, Any] | None = None,
    subject_type: str | None = None,
    subject_id: str | int | None = None,
    external_user_id: str | int | None = None,
    occurred_at: datetime | str | None = None,
) -> SyncOutboxEvent | None:
    """Persist an Operations event for retry by the sync worker."""
    envelope = _build_envelope(
        event_type,
        event_id,
        title=title,
        summary=summary,
        priority=priority,
        payload=payload,
        subject_type=subject_type,
        subject_id=subject_id,
        external_user_id=external_user_id,
        occurred_at=occurred_at,
    )
    if not settings.operations_integration_enabled:
        return None
    key = f'operations-v2:{event_id}'
    row = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.idempotency_key == key).first()
    if row:
        row.payload_json = json_dumps(envelope, ensure_ascii=False)
        if row.status not in {'synced', 'operations_pending'}:
            row.status = 'operations_pending'
            row.last_error = None
            row.next_retry_at = None
    else:
        row = SyncOutboxEvent(
            event_uuid=str(uuid.uuid4()),
            aggregate_type='operations_event',
            aggregate_id=int(subject_id) if str(subject_id or '').isdigit() else 0,
            event_type=f'{OPERATIONS_EVENT_PREFIX}{event_type}',
            idempotency_key=key,
            payload_json=json_dumps(envelope, ensure_ascii=False),
            status='operations_pending',
        )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _retry_at(retry_count: int) -> str:
    return (
        datetime.now(timezone.utc).replace(tzinfo=None)
        + timedelta(minutes=min(max(retry_count, 1) * 2, 30))
    ).replace(microsecond=0).isoformat()


async def run_operations_outbox_sync(
    db: Session,
    limit: int = 25,
    *,
    event_id: int | None = None,
) -> dict[str, int | bool]:
    """Deliver persisted Operations events with bounded exponential retry."""
    now_text = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
    query = (
        db.query(SyncOutboxEvent)
        .filter(SyncOutboxEvent.event_type.like(f'{OPERATIONS_EVENT_PREFIX}%'))
        .filter(SyncOutboxEvent.status.in_(['operations_pending', 'operations_retry']))
        .order_by(SyncOutboxEvent.id.asc())
    )
    if event_id is not None:
        query = query.filter(SyncOutboxEvent.id == int(event_id))
    rows = query.limit(max(1, min(int(limit or 25), 500))).all()
    processed = synced = retried = blocked = skipped = 0
    for row in rows:
        if row.next_retry_at and row.next_retry_at > now_text:
            skipped += 1
            continue
        if not settings.operations_integration_enabled:
            row.status = 'suppressed'
            row.last_error = 'Operations integration is disabled; no delivery was attempted.'
            row.next_retry_at = None
            db.add(row)
            db.commit()
            skipped += 1
            continue
        key = settings.operations_integration_key.strip()
        if not settings.operations_api_base.strip() or not key:
            row.status = 'operations_retry'
            row.retry_count = int(row.retry_count or 0) + 1
            row.last_error = 'Operations integration URL or key is not configured.'
            row.next_retry_at = _retry_at(row.retry_count)
            db.add(row)
            db.commit()
            retried += 1
            continue
        try:
            envelope = jsonable_encoder(json.loads(row.payload_json or '{}'))
        except Exception:
            row.status = 'operations_blocked'
            row.last_error = 'Operations event payload is not valid JSON.'
            row.next_retry_at = None
            db.add(row)
            db.commit()
            blocked += 1
            continue
        processed += 1
        row.last_attempt_at = now_text
        try:
            async with httpx.AsyncClient(
                timeout=settings.operations_integration_timeout_seconds,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    _operations_url(),
                    headers={'X-Integration-Api-Key': key},
                    json=envelope,
                )
            if 200 <= response.status_code < 300:
                row.status = 'synced'
                row.synced_at = now_text
                row.retry_count = 0
                row.next_retry_at = None
                row.last_error = None
                synced += 1
            elif response.status_code in {408, 425, 429} or response.status_code >= 500:
                row.status = 'operations_retry'
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = _retry_at(row.retry_count)
                row.last_error = f'Operations returned HTTP {response.status_code}: {response.text[:1000]}'
                retried += 1
            else:
                row.status = 'operations_blocked'
                row.retry_count = int(row.retry_count or 0) + 1
                row.next_retry_at = None
                row.last_error = f'Operations rejected the event with HTTP {response.status_code}: {response.text[:1000]}'
                blocked += 1
        except Exception as exc:
            row.status = 'operations_retry'
            row.retry_count = int(row.retry_count or 0) + 1
            row.next_retry_at = _retry_at(row.retry_count)
            row.last_error = f'Operations network failure: {exc}'[:2000]
            retried += 1
        db.add(row)
        db.commit()
    return {
        'ok': blocked == 0,
        'processed': processed,
        'synced': synced,
        'failed': retried,
        'retried': retried,
        'blocked': blocked,
        'skipped': skipped,
    }
