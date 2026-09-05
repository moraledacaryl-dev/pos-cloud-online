from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from sqlalchemy import and_, func, or_, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.migrations import migration_status
from app.core.rate_limit import get_rate_limit_status
from app.core.settings import settings
from app.models.entities import SyncOutboxEvent
from app.services.kds_stream_security import get_stream_ticket_store_status
from app.services.pos_service import outbox_suppression_reason, setting_json
from app.services.reliability_policy import evaluate_operational_readiness
from app.services.sync_service import get_sync_config


def _parse_iso(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def _age_seconds(value) -> int | None:
    parsed = _parse_iso(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))


def get_sync_worker_status(db: Session) -> dict:
    heartbeat = setting_json(db, 'sync_worker_heartbeat', default={}) or {}
    last_seen_at = heartbeat.get('last_seen_at')
    age_seconds = _age_seconds(last_seen_at)
    is_stale = age_seconds is None
    if age_seconds is not None:
        is_stale = age_seconds > int(settings.sync_worker_stale_seconds or max(120, settings.sync_worker_poll_seconds * 3))
    return {
        'last_seen_at': last_seen_at,
        'age_seconds': age_seconds,
        'is_stale': is_stale,
        'last_cycle': heartbeat.get('last_cycle') or {},
        'last_error': heartbeat.get('last_error'),
        'worker': heartbeat.get('worker') or {},
    }


def get_outbox_metrics(db: Session) -> dict:
    grouped = dict(db.query(SyncOutboxEvent.status, func.count(SyncOutboxEvent.id)).group_by(SyncOutboxEvent.status).all())
    suppressed_counts: dict[str, int] = {}
    suppressed_ids: list[int] = []
    if not settings.inventory_integration_enabled:
        suppressed_counts = {
            str(status): int(count or 0)
            for status, count in db.query(SyncOutboxEvent.status, func.count(SyncOutboxEvent.id)).filter(
                SyncOutboxEvent.event_type.like('inventory.%'),
                SyncOutboxEvent.status.in_(['pending', 'failed', 'error', 'blocked', 'inventory_pending', 'inventory_retry', 'suppressed']),
            ).group_by(SyncOutboxEvent.status).all()
        }
        suppressed_ids.extend(
            int(row_id)
            for (row_id,) in db.query(SyncOutboxEvent.id).filter(
                SyncOutboxEvent.event_type.like('inventory.%'),
                SyncOutboxEvent.status.in_(['pending', 'failed', 'error', 'blocked', 'inventory_pending', 'inventory_retry', 'suppressed']),
            ).all()
        )
    local_only_rows = db.query(SyncOutboxEvent).filter(
        SyncOutboxEvent.event_type.in_(['order.finalized', 'order.voided']),
        SyncOutboxEvent.status.in_(['pending', 'failed', 'error', 'blocked', 'suppressed']),
    ).all()
    for row in local_only_rows:
        if outbox_suppression_reason(row.event_type, row.payload_json):
            status = str(row.status)
            suppressed_counts[status] = suppressed_counts.get(status, 0) + 1
            suppressed_ids.append(int(row.id))
    suppressed = sum(suppressed_counts.values())
    pending = max(0, int(grouped.get('pending', 0)) - suppressed_counts.get('pending', 0))
    failed = max(
        0,
        int(grouped.get('failed', 0)) + int(grouped.get('error', 0))
        - suppressed_counts.get('failed', 0) - suppressed_counts.get('error', 0),
    )
    blocked = max(0, int(grouped.get('blocked', 0)) - suppressed_counts.get('blocked', 0))
    synced = int(grouped.get('synced', 0))
    retrying_query = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.retry_count > 0, SyncOutboxEvent.status != 'synced')
    if suppressed_ids:
        retrying_query = retrying_query.filter(SyncOutboxEvent.id.notin_(suppressed_ids))
    retrying = retrying_query.count()
    current_time = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    due_query = db.query(SyncOutboxEvent).filter(
        or_(
            SyncOutboxEvent.status == 'pending',
            and_(
                SyncOutboxEvent.status.in_(['failed', 'error']),
                or_(SyncOutboxEvent.next_retry_at.is_(None), SyncOutboxEvent.next_retry_at <= current_time),
            ),
        )
    )
    if suppressed_ids:
        due_query = due_query.filter(SyncOutboxEvent.id.notin_(suppressed_ids))
    due_now = due_query.count()

    unresolved_statuses = ['pending', 'failed', 'error', 'blocked']
    oldest_query = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.status.in_(unresolved_statuses))
    max_retry_query = db.query(func.max(SyncOutboxEvent.retry_count)).filter(SyncOutboxEvent.status.in_(unresolved_statuses))
    if suppressed_ids:
        oldest_query = oldest_query.filter(SyncOutboxEvent.id.notin_(suppressed_ids))
        max_retry_query = max_retry_query.filter(SyncOutboxEvent.id.notin_(suppressed_ids))
    oldest = oldest_query.order_by(SyncOutboxEvent.created_at.asc(), SyncOutboxEvent.id.asc()).first()
    max_retry_count = max_retry_query.scalar() or 0
    oldest_age_seconds = _age_seconds(getattr(oldest, 'created_at', None)) if oldest else None

    return {
        'total': int(sum(int(value or 0) for value in grouped.values())),
        'pending': pending,
        'failed': failed,
        'blocked': blocked,
        'suppressed': int(suppressed),
        'synced': synced,
        'retrying': int(retrying),
        'due_now': int(due_now),
        'attention_required': failed + blocked,
        'oldest_unresolved_event_id': getattr(oldest, 'id', None) if oldest else None,
        'oldest_unresolved_event_uuid': getattr(oldest, 'event_uuid', None) if oldest else None,
        'oldest_unresolved_status': getattr(oldest, 'status', None) if oldest else None,
        'oldest_unresolved_age_seconds': oldest_age_seconds,
        'max_retry_count': int(max_retry_count),
        'status_counts': {str(key): int(value or 0) for key, value in grouped.items()},
    }


def get_database_status(db: Session, engine: Engine) -> dict:
    db.execute(text('SELECT 1'))
    scheme = settings.database_url.split(':', 1)[0]
    return {
        'ok': True,
        'scheme': scheme,
        'migration': migration_status(engine),
    }


async def get_accounting_api_status(db: Session) -> dict:
    config = get_sync_config(db)
    base = (config.get('api_base') or '').strip()
    if not base:
        return {'ok': False, 'configured': False, 'status': 'not_configured'}
    health_path = (config.get('healthcheck_path') or '/healthz').strip()
    url = _accounting_health_url(base, health_path)
    try:
        async with httpx.AsyncClient(timeout=settings.health_timeout_seconds) as client:
            response = await client.get(url)
        return {
            'ok': response.status_code < 400,
            'configured': True,
            'url': url,
            'status_code': response.status_code,
            'reachable': True,
        }
    except Exception as exc:
        return {
            'ok': False,
            'configured': True,
            'url': url,
            'reachable': False,
            'error': str(exc),
        }


def _accounting_health_url(base: str, health_path: str) -> str:
    parsed = urlsplit(base)
    return urlunsplit((parsed.scheme, parsed.netloc, '/' + health_path.lstrip('/'), '', '')) if health_path.startswith('/') else base.rstrip('/') + '/' + health_path


def get_security_readiness() -> dict:
    warnings = settings.security_warnings
    return {
        'ok': not warnings,
        'warnings': warnings,
    }


async def build_health_report(db: Session, engine: Engine) -> dict:
    database = get_database_status(db, engine)
    accounting_api = await get_accounting_api_status(db)
    sync_worker = get_sync_worker_status(db)
    outbox = get_outbox_metrics(db)
    rate_limit = get_rate_limit_status()
    ticket_store = get_stream_ticket_store_status()
    security = get_security_readiness()

    readiness = evaluate_operational_readiness(
        database_ok=bool(database.get('ok')),
        migrations_ok=bool(database.get('migration', {}).get('ok')) and not bool(database.get('migration', {}).get('requires_upgrade')),
        security_ok=bool(security.get('ok')),
        worker_stale=bool(sync_worker.get('is_stale')),
        failed_events=int(outbox.get('failed', 0)),
        blocked_events=int(outbox.get('blocked', 0)),
        accounting_configured=bool(accounting_api.get('configured')),
        # A downstream HTTP response proves network reachability, but a 4xx/5xx
        # health response is still an unhealthy integration and must degrade the
        # strict integration-readiness endpoint.
        accounting_reachable=bool(accounting_api.get('ok', False)),
        kds_ticket_store_required=bool(ticket_store.get('required')),
        kds_ticket_store_reachable=bool(ticket_store.get('connected')),
    )

    return {
        'ok': readiness['ok'],
        'status': readiness['status'],
        'sales_ready': readiness['sales_ready'],
        'integrations_ready': readiness['integrations_ready'],
        'reasons': readiness['reasons'],
        'environment': settings.environment,
        'database': database,
        'security': security,
        'rate_limit': rate_limit,
        'kds_stream_ticket_store': ticket_store,
        'accounting_api': accounting_api,
        'sync_worker': sync_worker,
        'outbox': outbox,
        'integration_reachability': {
            'accounting_api': accounting_api.get('reachable', False),
            'redis': ticket_store.get('connected', False) if ticket_store.get('required') else None,
        },
    }
