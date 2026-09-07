import asyncio
import json
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import operations_integration as oi


def test_operations_url_accepts_api_base(monkeypatch):
    monkeypatch.setattr(oi.settings, 'operations_api_base', 'https://operations.hiddenoasis.app/api')
    monkeypatch.setattr(oi.settings, 'operations_source_app', 'dedicated_pos_cloud')
    assert oi._operations_url() == 'https://operations.hiddenoasis.app/api/integrations/v2/events/dedicated_pos_cloud'


def test_publisher_uses_stable_event_contract(monkeypatch):
    captured = {}
    class Response:
        def raise_for_status(self):
            return None
    def fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(oi.settings, 'operations_integration_enabled', True)
    monkeypatch.setattr(oi.settings, 'operations_api_base', 'https://operations.hiddenoasis.app/api')
    monkeypatch.setattr(oi.settings, 'operations_integration_key', 'test-key')
    monkeypatch.setattr(oi.settings, 'operations_source_app', 'dedicated_pos_cloud')
    monkeypatch.setattr(oi.httpx, 'post', fake_post)

    when = datetime(2026, 9, 1, 8, 30, tzinfo=timezone.utc)
    assert oi.publish_operations_event(
        'cash_movement.created',
        'cash-movement:42',
        title='POS cash movement',
        subject_type='cash_movement',
        subject_id=42,
        occurred_at=when,
        payload={'movement_id': 42},
    ) is True
    assert captured['headers']['X-Integration-Api-Key'] == 'test-key'
    assert captured['json']['event_id'] == 'cash-movement:42'
    assert captured['json']['event_type'] == 'cash_movement.created'
    assert captured['json']['subject']['id'] == '42'
    assert captured['json']['occurred_at'] == '2026-09-01T08:30:00+00:00'


def test_unknown_event_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match='does not accept'):
        oi.publish_operations_event('private.pos.event', 'x', title='x')


def test_operations_events_are_durable_and_worker_delivers_them(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    monkeypatch.setattr(oi.settings, 'operations_integration_enabled', True)
    monkeypatch.setattr(oi.settings, 'operations_api_base', 'https://operations.hiddenoasis.app/api')
    monkeypatch.setattr(oi.settings, 'operations_integration_key', 'test-key')

    row = oi.enqueue_operations_event(
        db,
        'order.finalized',
        'order-finalized:42',
        title='Order finalized',
        payload={'total': 100.25},
        subject_type='order',
        subject_id=42,
    )
    assert row is not None
    assert row.status == 'operations_pending'
    assert json.loads(row.payload_json)['event_id'] == 'order-finalized:42'

    captured = {}

    class Response:
        status_code = 202
        text = ''

    class Client:
        def __init__(self, **kwargs):
            captured['client'] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured['url'] = url
            captured.update(kwargs)
            return Response()

    monkeypatch.setattr(oi.httpx, 'AsyncClient', Client)
    result = asyncio.run(oi.run_operations_outbox_sync(db, limit=10))
    db.refresh(row)
    assert result['synced'] == 1
    assert row.status == 'synced'
    assert captured['headers']['X-Integration-Api-Key'] == 'test-key'
    assert captured['json']['subject']['id'] == '42'

    duplicate = oi.enqueue_operations_event(
        db,
        'order.finalized',
        'order-finalized:42',
        title='Order finalized',
        subject_type='order',
        subject_id=42,
    )
    assert duplicate.id == row.id
    assert db.query(SyncOutboxEvent).count() == 1
