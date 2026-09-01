from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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
