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
from app.services.pos_service import setting_json
from app.services.sync_service import get_sync_config


def _parse_iso(value: str | None):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None


def get_sync_worker_status(db: Session) -> dict:
    heartbeat = setting_json(db, 'sync_worker_heartbeat', default={}) or {}
    last_seen_at = heartbeat.get('last_seen_at')
    parsed = _parse_iso(last_seen_at)
    age_seconds = None
    is_stale = True
    if parsed is not None:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_seconds = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
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
    pending = int(grouped.get('pending', 0))
    failed = int(grouped.get('failed', 0) or grouped.get('error', 0))
    synced = int(grouped.get('synced', 0))
    retrying = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.retry_count > 0, SyncOutboxEvent.status != 'synced').count()
    current_time = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0).isoformat()
    due_now = db.query(SyncOutboxEvent).filter(
        or_(
            SyncOutboxEvent.status == 'pending',
            and_(
                SyncOutboxEvent.status == 'failed',
                or_(SyncOutboxEvent.next_retry_at.is_(None), SyncOutboxEvent.next_retry_at <= current_time),
            ),
        )
    ).count()
    blocked = int(grouped.get('blocked', 0))
    return {
        'total': pending + failed + synced,
        'pending': pending,
        'failed': failed,
        'blocked': blocked,
        'synced': synced,
        'retrying': int(retrying),
        'due_now': int(due_now),
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


async def build_health_report(db: Session, engine: Engine) -> dict:
    database = get_database_status(db, engine)
    accounting_api = await get_accounting_api_status(db)
    sync_worker = get_sync_worker_status(db)
    outbox = get_outbox_metrics(db)
    return {
        'ok': bool(database.get('ok')) and bool(database.get('migration', {}).get('ok')),
        'environment': settings.environment,
        'database': database,
        'rate_limit': get_rate_limit_status(),
        'accounting_api': accounting_api,
        'sync_worker': sync_worker,
        'outbox': outbox,
        'integration_reachability': {
            'accounting_api': accounting_api.get('reachable', False),
            'redis': get_rate_limit_status().get('connected', False),
        },
    }
