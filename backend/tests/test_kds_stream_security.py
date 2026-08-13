import asyncio
import inspect

import httpx
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.api import kitchen
from app.main import app
from app.services.kds_stream import broadcaster_metrics, stream_kds_events
from app.services.kds_stream_security import (
    acquire_stream_slot,
    active_stream_metrics,
    clear_test_stream_tickets,
    consume_stream_ticket,
    get_stream_ticket_store_status,
    issue_stream_ticket,
    release_stream_slot,
)


def setup_function():
    clear_test_stream_tickets()


def test_stream_ticket_is_opaque_station_bound_and_single_use(monkeypatch):
    monkeypatch.setattr('app.services.kds_stream_security.settings.environment', 'test')
    issued = issue_stream_ticket(user_id=41, station='kitchen', device_id='tablet-a')
    assert '41' not in issued['ticket']
    assert len(issued['ticket']) >= 32

    payload = consume_stream_ticket(issued['ticket'], requested_station='kitchen')
    assert payload['user_id'] == 41
    assert payload['station'] == 'kitchen'
    assert payload['device_id'] == 'tablet-a'

    with pytest.raises(ValueError, match='invalid, expired, or already used'):
        consume_stream_ticket(issued['ticket'], requested_station='kitchen')


def test_stream_ticket_cannot_be_substituted_to_another_station(monkeypatch):
    monkeypatch.setattr('app.services.kds_stream_security.settings.environment', 'test')
    issued = issue_stream_ticket(user_id=7, station='bar')
    with pytest.raises(ValueError, match='different station'):
        consume_stream_ticket(issued['ticket'], requested_station='kitchen')
    with pytest.raises(ValueError, match='invalid, expired, or already used'):
        consume_stream_ticket(issued['ticket'], requested_station='bar')


def test_stream_ticket_expiry_is_enforced(monkeypatch):
    monkeypatch.setattr('app.services.kds_stream_security.settings.environment', 'test')
    clock = {'now': 1000.0}
    monkeypatch.setattr('app.services.kds_stream_security.time.time', lambda: clock['now'])
    issued = issue_stream_ticket(user_id=8, station='expo')
    clock['now'] = 2000.0
    with pytest.raises(ValueError, match='invalid, expired, or already used'):
        consume_stream_ticket(issued['ticket'], requested_station='expo')


def test_stream_limit_is_enforced_and_released(monkeypatch):
    monkeypatch.setattr('app.services.kds_stream_security.settings.kds_stream_max_per_user', 2)

    async def scenario():
        await acquire_stream_slot(99)
        await acquire_stream_slot(99)
        with pytest.raises(ValueError, match='Too many active KDS streams'):
            await acquire_stream_slot(99)
        metrics = await active_stream_metrics()
        assert metrics['active_streams'] >= 2
        await release_stream_slot(99)
        await release_stream_slot(99)
        metrics = await active_stream_metrics()
        assert metrics['active_streams'] == 0

    asyncio.run(scenario())


def test_stream_generator_unsubscribes_on_close():
    async def scenario():
        before = await broadcaster_metrics()
        generator = stream_kds_events('kitchen', keepalive_seconds=1, max_lifetime_seconds=60)
        hello = await anext(generator)
        assert 'event: hello' in hello
        during = await broadcaster_metrics()
        assert during['listeners'] == before['listeners'] + 1
        await generator.aclose()
        after = await broadcaster_metrics()
        assert after['listeners'] == before['listeners']

    asyncio.run(scenario())


def test_stream_route_has_no_request_scoped_database_dependency():
    signature = inspect.signature(kitchen.stream)
    assert 'db' not in signature.parameters
    source = inspect.getsource(kitchen.stream)
    assert 'Depends(get_db)' not in source
    assert 'SessionLocal' not in source


def test_legacy_access_token_query_parameter_no_longer_authenticates_stream():
    async def scenario():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url='http://test') as client:
            response = await client.get('/api/kitchen/stream?token=definitely-not-a-stream-ticket')
        assert response.status_code == 422
        body = response.json()
        assert any(error.get('loc', [])[-1:] == ['ticket'] for error in body.get('detail', []))

    asyncio.run(scenario())


def test_ticket_store_readiness_does_not_infer_redis_from_memory_rate_limit(monkeypatch):
    class UnreachableRedis:
        def ping(self):
            raise RedisConnectionError('unreachable')

    monkeypatch.setattr('app.services.kds_stream_security.settings.environment', 'production')
    monkeypatch.setattr('app.services.kds_stream_security._redis_client', lambda: UnreachableRedis())
    status = get_stream_ticket_store_status()
    assert status == {'backend': 'redis', 'required': True, 'connected': False}


def test_development_ticket_store_reports_memory_without_claiming_redis(monkeypatch):
    monkeypatch.setattr('app.services.kds_stream_security.settings.environment', 'development')
    status = get_stream_ticket_store_status()
    assert status == {'backend': 'memory', 'required': False, 'connected': True}
