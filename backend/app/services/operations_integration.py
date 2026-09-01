import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi.encoders import jsonable_encoder

from app.core.settings import settings

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


def _operations_url() -> str:
    base = settings.operations_api_base.rstrip('/')
    suffix = f'/integrations/v2/events/{settings.operations_source_app}'
    if base.endswith(suffix):
        return base
    if base.endswith('/api'):
        return f'{base}{suffix}'
    return f'{base}/api{suffix}'


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
    """Best-effort delivery to Operations; POS transactions never depend on it.

    The source event id and occurred_at should come from the durable POS business
    record whenever possible so a repeated delivery is byte-for-byte idempotent.
    """
    if event_type not in OPERATIONS_EVENT_TYPES:
        raise ValueError(f'Operations v2 does not accept {event_type}')
    if not settings.operations_integration_enabled:
        return False
    key = settings.operations_integration_key.strip()
    if not settings.operations_api_base.strip() or not key:
        logger.warning('operations.integration_not_configured', extra={'event_type': event_type})
        return False
    if occurred_at is None:
        occurred_at = datetime.now(timezone.utc)
    envelope = {
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
    try:
        response = httpx.post(
            _operations_url(),
            headers={'X-Integration-Api-Key': key},
            json=jsonable_encoder(envelope),
            timeout=settings.operations_integration_timeout_seconds,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning(
            'operations.integration_delivery_failed',
            extra={'event_type': event_type, 'event_id': str(event_id), 'error': str(exc)},
        )
        return False
