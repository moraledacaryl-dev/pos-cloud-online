from __future__ import annotations

from collections import defaultdict, deque
from time import time

from fastapi import HTTPException

from app.core.settings import settings

try:
    import redis
except Exception:  # pragma: no cover - optional during local static analysis
    redis = None


_BUCKETS: dict[str, deque] = defaultdict(deque)
_REDIS_CLIENT = None
_BACKEND = 'memory'


def init_rate_limiter():
    global _REDIS_CLIENT, _BACKEND
    desired = (settings.rate_limit_backend or ('redis' if settings.is_production else 'memory')).strip().lower()
    _REDIS_CLIENT = None
    if not settings.rate_limit_enabled:
        _BACKEND = 'disabled'
        return {'backend': _BACKEND, 'connected': True}
    if desired == 'redis':
        if not settings.redis_url:
            if settings.is_production:
                raise RuntimeError('REDIS_URL is required in production when rate limiting is enabled.')
            _BACKEND = 'memory'
            return {'backend': _BACKEND, 'connected': False}
        if redis is None:
            if settings.is_production:
                raise RuntimeError('redis package is required for Redis-backed rate limiting in production.')
            _BACKEND = 'memory'
            return {'backend': _BACKEND, 'connected': False}
        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        _REDIS_CLIENT = client
        _BACKEND = 'redis'
        return {'backend': _BACKEND, 'connected': True}
    _BACKEND = 'memory'
    return {'backend': _BACKEND, 'connected': True}


def get_rate_limit_status() -> dict:
    return {
        'enabled': bool(settings.rate_limit_enabled),
        'backend': _BACKEND,
        'connected': bool(_BACKEND in {'disabled', 'memory'} or _REDIS_CLIENT is not None),
    }


def _enforce_memory_limit(key: str, max_hits: int, window_seconds: int):
    bucket = _BUCKETS[key]
    now = time()
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= max_hits:
        raise HTTPException(status_code=429, detail='Too many requests. Please retry shortly.')
    bucket.append(now)


def _enforce_redis_limit(key: str, max_hits: int, window_seconds: int):
    if _REDIS_CLIENT is None:
        if settings.is_production:
            raise HTTPException(status_code=503, detail='Rate limiter is unavailable.')
        return _enforce_memory_limit(key, max_hits, window_seconds)
    window_bucket = int(time() // window_seconds)
    redis_key = f"{settings.rate_limit_redis_prefix}:{key}:{window_bucket}"
    try:
        hits = int(_REDIS_CLIENT.incr(redis_key))
        if hits == 1:
            _REDIS_CLIENT.expire(redis_key, int(window_seconds) + 5)
    except Exception as exc:
        if settings.is_production:
            raise HTTPException(status_code=503, detail='Rate limiter is unavailable.') from exc
        return _enforce_memory_limit(key, max_hits, window_seconds)
    if hits > max_hits:
        raise HTTPException(status_code=429, detail='Too many requests. Please retry shortly.')


def enforce_rate_limit(key: str, limit: int | None = None, window_seconds: int = 60):
    if not settings.rate_limit_enabled:
        return
    max_hits = int(limit or settings.rate_limit_per_minute)
    if _BACKEND == 'redis':
        return _enforce_redis_limit(key, max_hits, window_seconds)
    return _enforce_memory_limit(key, max_hits, window_seconds)
