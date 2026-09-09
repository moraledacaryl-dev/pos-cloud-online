import asyncio
import json
from types import SimpleNamespace

from app.services import inventory_integration as integration


def order_payload(**overrides):
    payload = {
        'id': 15,
        'order_uuid': 'order-uuid-15',
        'order_no': 'POS-20260809-0015',
        'status': 'paid',
        'refund_status': 'none',
        'lines': [
            {'catalog_item_id': 1, 'sku_code': 'CAFE-001', 'external_sku_id': 101, 'item_name_snapshot': 'Coffee', 'quantity': 2},
            {'catalog_item_id': 2, 'sku_code': None, 'external_sku_id': 202, 'item_name_snapshot': 'Cake', 'quantity': 1},
        ],
    }
    payload.update(overrides)
    return payload


def test_inventory_sale_payload_uses_stable_order_uuid_and_product_ids():
    event = integration.build_inventory_event(order_payload(), 'sale_completed')
    assert event['external_event_id'] == 'pos:order-uuid-15:sale_completed'
    assert event['external_sale_id'] == 'order-uuid-15'
    assert event['pos_system'] == 'hidden-oasis-pos'
    assert event['lines'] == [
        {'external_product_id': 'CAFE-001', 'quantity': 2.0},
        {'external_product_id': '202', 'quantity': 1.0},
    ]
    assert event['_unmapped_lines'] == []


def test_unmapped_pos_line_is_retained_as_actionable_blocker():
    event = integration.build_inventory_event(
        order_payload(lines=[{'catalog_item_id': 9, 'sku_code': None, 'external_sku_id': None, 'item_name_snapshot': 'Emergency item', 'quantity': 1}]),
        'sale_completed',
    )
    assert event['lines'] == []
    assert event['_unmapped_lines'][0]['item_name'] == 'Emergency item'


def test_inventory_reversal_policy_never_reverses_partial_refund():
    assert integration.should_reverse_inventory_for_refund({'refund_status': 'partially_refunded'}) is False
    assert integration.should_reverse_inventory_for_refund({'refund_status': 'fully_refunded'}) is True


def test_inventory_void_reversal_only_applies_after_finalization():
    assert integration.should_reverse_inventory_for_void({'status': 'draft'}) is False
    assert integration.should_reverse_inventory_for_void({'status': 'served'}) is False
    assert integration.should_reverse_inventory_for_void({'status': 'paid'}) is True
    assert integration.should_reverse_inventory_for_void({'status': 'folio_pending'}) is True


def test_inventory_outbox_uses_dedicated_pending_status(monkeypatch):
    row = SimpleNamespace(status='pending', last_error='old')
    captured = {}

    def fake_create_outbox_event(db, **kwargs):
        captured.update(kwargs)
        return row

    class FakeDb:
        def add(self, value):
            assert value is row
        def commit(self):
            pass
        def refresh(self, value):
            assert value is row

    monkeypatch.setattr(integration, 'create_outbox_event', fake_create_outbox_event)
    result = integration.enqueue_inventory_event(FakeDb(), order_payload(), 'sale_completed')

    assert result is row
    assert row.status == 'inventory_pending'
    assert row.last_error is None
    assert captured['event_type'] == 'inventory.sale_completed'
    assert captured['idempotency_key'] == 'inventory:pos:order-uuid-15:sale_completed'


def test_inventory_worker_follows_canonical_redirects(monkeypatch):
    payload = integration.build_inventory_event(order_payload(), 'sale_completed')
    row = SimpleNamespace(
        id=101,
        event_type='inventory.sale_completed',
        status='inventory_pending',
        next_retry_at=None,
        retry_count=0,
        last_attempt_at=None,
        synced_at=None,
        last_error=None,
        payload_json=json.dumps(payload),
    )
    captured = {}

    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self
        def order_by(self, *args, **kwargs):
            return self
        def limit(self, *args, **kwargs):
            return self
        def all(self):
            return [row]

    class FakeDb:
        def query(self, *args, **kwargs):
            return FakeQuery()
        def add(self, value):
            assert value is row
        def commit(self):
            pass

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

    monkeypatch.setattr(integration.settings, 'inventory_integration_enabled', True)
    monkeypatch.setattr(integration.settings, 'inventory_api_base', 'https://inventory.hiddenoasis.app/api')
    monkeypatch.setattr(integration.settings, 'inventory_integration_token', 'inventory-test-token')
    monkeypatch.setattr(integration.settings, 'inventory_pos_events_path', '/integrations/pos/events')
    monkeypatch.setattr(integration.httpx, 'AsyncClient', Client)

    result = asyncio.run(integration.run_inventory_outbox_sync(FakeDb(), limit=10))

    assert result['synced'] == 1
    assert row.status == 'synced'
    assert captured['client']['follow_redirects'] is True
    assert captured['client']['headers']['X-Integration-Token'] == 'inventory-test-token'
    assert captured['url'] == 'https://inventory.hiddenoasis.app/api/integrations/pos/events'
