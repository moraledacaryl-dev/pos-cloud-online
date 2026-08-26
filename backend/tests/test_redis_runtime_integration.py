import os

import pytest
from fastapi import HTTPException
from redis import Redis

if os.getenv('RUN_REDIS_INTEGRATION') != '1':
    pytest.skip('Redis integration test is enabled only in the production-equivalent CI job.', allow_module_level=True)

from app.core import rate_limit
from app.core.settings import settings
from app.services import kds_stream_security


def test_real_redis_rate_limiter_enforces_limit(monkeypatch):
    redis_url = os.environ['REDIS_URL']
    client = Redis.from_url(redis_url, decode_responses=True)
    assert client.ping() is True

    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(settings, 'rate_limit_backend', 'redis')
    monkeypatch.setattr(settings, 'redis_url', redis_url)
    monkeypatch.setattr(settings, 'rate_limit_redis_prefix', 'pos-ci:ratelimit')

    status = rate_limit.init_rate_limiter()
    assert status == {'backend': 'redis', 'connected': True}
    key = 'pass9-redis-limit'
    rate_limit.enforce_rate_limit(key, limit=2, window_seconds=30)
    rate_limit.enforce_rate_limit(key, limit=2, window_seconds=30)
    with pytest.raises(HTTPException) as exc:
        rate_limit.enforce_rate_limit(key, limit=2, window_seconds=30)
    assert exc.value.status_code == 429


def test_real_redis_kds_ticket_is_one_use_and_station_bound(monkeypatch):
    redis_url = os.environ['REDIS_URL']
    monkeypatch.setattr(settings, 'environment', 'staging')
    monkeypatch.setattr(settings, 'redis_url', redis_url)
    monkeypatch.setattr(settings, 'kds_stream_ticket_ttl_seconds', 30)

    status = kds_stream_security.get_stream_ticket_store_status()
    assert status == {'backend': 'redis', 'required': True, 'connected': True}

    issued = kds_stream_security.issue_stream_ticket(user_id=5001, station='kitchen', device_id='ci-tablet')
    payload = kds_stream_security.consume_stream_ticket(issued['ticket'], requested_station='kitchen')
    assert payload['user_id'] == 5001
    assert payload['device_id'] == 'ci-tablet'

    with pytest.raises(ValueError, match='already used'):
        kds_stream_security.consume_stream_ticket(issued['ticket'], requested_station='kitchen')

    second = kds_stream_security.issue_stream_ticket(user_id=5001, station='bar', device_id='ci-tablet')
    with pytest.raises(ValueError, match='different station'):
        kds_stream_security.consume_stream_ticket(second['ticket'], requested_station='kitchen')
