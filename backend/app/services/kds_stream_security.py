from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import threading
import time
from collections import defaultdict

from redis import Redis
from redis.exceptions import RedisError

from app.core.settings import settings

_TICKET_PREFIX = 'dedicated-pos:kds:ticket:'
_memory_tickets: dict[str, tuple[float, dict]] = {}
_memory_lock = threading.Lock()
_active_lock = asyncio.Lock()
_active_by_user: dict[int, int] = defaultdict(int)
_active_total = 0


def _ticket_hash(ticket: str) -> str:
    return hashlib.sha256(ticket.encode('utf-8')).hexdigest()


def _redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2)


def _use_memory_store() -> bool:
    return settings.environment.strip().lower() in {'test', 'development'}


def get_stream_ticket_store_status() -> dict:
    """Report the actual backing store used by KDS stream tickets.

    Test/development intentionally use process-local memory. Production/staging
    require Redis because one-use tickets must survive normal request concurrency
    without relying on a single Python process. Never infer Redis health from the
    unrelated rate-limit backend.
    """
    if _use_memory_store():
        return {'backend': 'memory', 'required': False, 'connected': True}
    try:
        connected = bool(_redis_client().ping())
        return {'backend': 'redis', 'required': True, 'connected': connected}
    except RedisError:
        return {'backend': 'redis', 'required': True, 'connected': False}


def issue_stream_ticket(*, user_id: int, station: str | None, device_id: str | None = None) -> dict:
    ticket = secrets.token_urlsafe(32)
    digest = _ticket_hash(ticket)
    now = int(time.time())
    ttl = max(10, min(int(settings.kds_stream_ticket_ttl_seconds), 120))
    payload = {
        'user_id': int(user_id),
        'station': (station or '').strip().lower(),
        'device_id': (device_id or '').strip()[:128],
        'issued_at': now,
        'expires_at': now + ttl,
    }
    key = f'{_TICKET_PREFIX}{digest}'
    if _use_memory_store():
        with _memory_lock:
            _memory_tickets[key] = (time.time() + ttl, payload)
    else:
        try:
            client = _redis_client()
            client.set(key, json.dumps(payload, separators=(',', ':')), ex=ttl, nx=True)
        except RedisError as exc:
            raise RuntimeError('KDS stream ticket store is unavailable.') from exc
    return {'ticket': ticket, 'expires_in': ttl, 'station': payload['station']}


def consume_stream_ticket(ticket: str, *, requested_station: str | None) -> dict:
    raw_ticket = (ticket or '').strip()
    if not raw_ticket:
        raise ValueError('Missing stream ticket.')
    key = f'{_TICKET_PREFIX}{_ticket_hash(raw_ticket)}'
    raw = None
    if _use_memory_store():
        with _memory_lock:
            item = _memory_tickets.pop(key, None)
        if item:
            expires_at, payload = item
            if expires_at > time.time():
                raw = json.dumps(payload)
    else:
        try:
            client = _redis_client()
            raw = client.getdel(key)
        except RedisError as exc:
            raise RuntimeError('KDS stream ticket store is unavailable.') from exc
    if not raw:
        raise ValueError('Stream ticket is invalid, expired, or already used.')
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise ValueError('Stream ticket is invalid.') from exc
    expected_station = str(payload.get('station') or '').strip().lower()
    actual_station = str(requested_station or '').strip().lower()
    if expected_station != actual_station:
        raise ValueError('Stream ticket is scoped to a different station.')
    if int(payload.get('expires_at') or 0) <= int(time.time()):
        raise ValueError('Stream ticket has expired.')
    return payload


async def acquire_stream_slot(user_id: int) -> None:
    global _active_total
    limit = max(1, int(settings.kds_stream_max_per_user))
    async with _active_lock:
        if _active_by_user[int(user_id)] >= limit:
            raise ValueError('Too many active KDS streams for this user/device.')
        _active_by_user[int(user_id)] += 1
        _active_total += 1


async def release_stream_slot(user_id: int) -> None:
    global _active_total
    async with _active_lock:
        uid = int(user_id)
        if _active_by_user.get(uid, 0) > 0:
            _active_by_user[uid] -= 1
            _active_total = max(0, _active_total - 1)
            if _active_by_user[uid] <= 0:
                _active_by_user.pop(uid, None)


async def active_stream_metrics() -> dict:
    async with _active_lock:
        return {
            'active_streams': int(_active_total),
            'active_users': len(_active_by_user),
            'max_per_user': max(1, int(settings.kds_stream_max_per_user)),
        }


def clear_test_stream_tickets() -> None:
    with _memory_lock:
        _memory_tickets.clear()
