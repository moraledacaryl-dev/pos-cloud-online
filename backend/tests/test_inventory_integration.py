import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
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
    assert integration.should_reverse_inventory_for_refund({'refund_status': 'fully_refunded'}) is False


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



def test_inventory_outbox_deferred_commit_only_flushes(monkeypatch):
    row = SimpleNamespace(status='pending', last_error='old')
    calls = {'commits': 0, 'flushes': 0, 'refreshes': 0}

    monkeypatch.setattr(integration, 'create_outbox_event', lambda db, **kwargs: row)

    class FakeDb:
        def add(self, value):
            assert value is row
        def commit(self):
            calls['commits'] += 1
        def flush(self):
            calls['flushes'] += 1
        def refresh(self, value):
            assert value is row
            calls['refreshes'] += 1

    result = integration.enqueue_inventory_event(FakeDb(), order_payload(), 'sale_completed', commit=False)
    assert result is row
    assert row.status == 'inventory_pending'
    assert calls == {'commits': 0, 'flushes': 1, 'refreshes': 1}




def test_each_physical_return_has_unique_event_id():
    first = integration.build_inventory_event(
        order_payload(), 'sale_returned',
        return_lines=[{'external_product_id': 'CAFE-001', 'quantity': 1, 'inventory_disposition': 'waste'}],
        return_id='refund-101',
    )
    second = integration.build_inventory_event(
        order_payload(), 'sale_returned',
        return_lines=[{'external_product_id': 'CAFE-001', 'quantity': 1, 'inventory_disposition': 'waste'}],
        return_id='refund-102',
    )
    assert first['external_event_id'] == 'pos:order-uuid-15:sale_returned:refund-101'
    assert second['external_event_id'] == 'pos:order-uuid-15:sale_returned:refund-102'
    assert first['external_event_id'] != second['external_event_id']
    assert first['lines'] == [{'external_product_id': 'CAFE-001', 'quantity': 1.0, 'inventory_disposition': 'waste'}]


def test_physical_return_requires_refund_id():
    import pytest

    with pytest.raises(ValueError, match='unique refund identifier'):
        integration.build_inventory_event(
            order_payload(), 'sale_returned',
            return_lines=[{'external_product_id': 'CAFE-001', 'quantity': 1, 'inventory_disposition': 'waste'}],
        )



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


def test_inventory_event_is_suppressed_not_lost_when_delivery_disabled(monkeypatch):
    row = SimpleNamespace(status='inventory_pending', last_error=None)

    class FakeQuery:
        def filter(self, *args, **kwargs): return self
        def order_by(self, *args, **kwargs): return self
        def limit(self, *args, **kwargs): return self
        def all(self): return [row]

    class FakeDb:
        def query(self, *args, **kwargs): return FakeQuery()
        def add(self, value): pass
        def commit(self): pass

    monkeypatch.setattr(integration.settings, 'inventory_integration_enabled', False)
    result = asyncio.run(integration.run_inventory_outbox_sync(FakeDb(), limit=10))
    assert result['skipped'] == 1
    assert row.status == 'suppressed'
    assert 'not enabled' in row.last_error


def test_financial_refund_never_implies_physical_stock_return():
    assert integration.should_reverse_inventory_for_refund({'refund_status': 'partially_refunded'}) is False
    assert integration.should_reverse_inventory_for_refund({'refund_status': 'fully_refunded'}) is False



@pytest.mark.parametrize('quantity', ['NaN', 'Infinity', '-1', 0, '0.00001', 'bad quantity'])
def test_inventory_sale_rejects_invalid_or_rounded_away_quantity(quantity):
    with pytest.raises(ValueError, match='positive and finite'):
        integration.build_inventory_event(
            order_payload(lines=[
                {'sku_code': 'CAFE-001', 'item_name_snapshot': 'Coffee', 'quantity': quantity},
            ]),
            'sale_completed',
        )


def test_inventory_quantity_precision_is_normalized_to_pos_line_precision():
    payload = integration.build_inventory_event(
        order_payload(lines=[
            {'sku_code': 'CAFE-001', 'item_name_snapshot': 'Coffee', 'quantity': '1.23456'},
        ]),
        'sale_completed',
    )
    assert payload['lines'][0]['quantity'] == 1.2346


def test_empty_physical_return_is_rejected_before_transaction_commit():
    with pytest.raises(ValueError, match='at least one mapped'):
        integration.build_inventory_event(
            order_payload(), 'sale_returned',
            return_lines=[], return_id='refund-123',
        )


def _inventory_outbox_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def test_void_uses_original_sale_sku_and_quantity_after_catalog_change():
    db = _inventory_outbox_session()
    sale_payload = integration.build_inventory_event(order_payload(), 'sale_completed')
    original = SyncOutboxEvent(
        event_uuid=str(uuid.uuid4()),
        aggregate_type='order', aggregate_id=15,
        event_type='inventory.sale_completed',
        idempotency_key='inventory:pos:order-uuid-15:sale_completed',
        payload_json=json.dumps(sale_payload),
        status='synced',
    )
    db.add(original)
    db.commit()

    updated_order = order_payload(lines=[
        {'sku_code': 'REPLACEMENT-999', 'external_sku_id': 999, 'quantity': 999},
    ])
    result = integration.enqueue_inventory_event(db, updated_order, 'sale_voided', commit=False)
    reversed_payload = json.loads(result.payload_json)
    assert reversed_payload['external_event_id'] == 'pos:order-uuid-15:sale_voided'
    assert reversed_payload['lines'] == sale_payload['lines']
    assert reversed_payload['lines'][0]['external_product_id'] == 'CAFE-001'
    assert result.status == 'inventory_pending'
    db.close()


def test_void_with_corrupted_original_sale_mapping_fails_closed():
    db = _inventory_outbox_session()
    db.add(SyncOutboxEvent(
        event_uuid=str(uuid.uuid4()), aggregate_type='order', aggregate_id=15,
        event_type='inventory.sale_completed',
        idempotency_key='inventory:pos:order-uuid-15:sale_completed',
        payload_json='{"external_sale_id":"another-order","lines":[]}',
        status='synced',
    ))
    db.commit()
    with pytest.raises(ValueError, match='Original Inventory sale mapping is invalid'):
        integration.enqueue_inventory_event(db, order_payload(), 'sale_voided', commit=False)
    db.rollback()
    assert db.query(SyncOutboxEvent).count() == 1
    db.close()


def _stub_inventory_worker(monkeypatch, response_status=202):
    calls = {'posts': 0}

    class Response:
        status_code = response_status
        text = 'Temporary upstream limit' if response_status != 202 else ''

    class Client:
        def __init__(self, **_kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None
        async def post(self, *_args, **_kwargs):
            calls['posts'] += 1
            return Response()

    monkeypatch.setattr(integration.settings, 'inventory_integration_enabled', True)
    monkeypatch.setattr(integration.settings, 'inventory_api_base', 'https://inventory.hiddenoasis.app/api')
    monkeypatch.setattr(integration.settings, 'inventory_integration_token', 'test-token')
    monkeypatch.setattr(integration.httpx, 'AsyncClient', Client)
    return calls


def test_inventory_reversal_waits_for_original_sale_to_sync(monkeypatch):
    sale = SimpleNamespace(status='inventory_retry')
    row = SimpleNamespace(
        id=25, aggregate_id=15, event_type='inventory.sale_voided',
        status='inventory_pending', next_retry_at=None, retry_count=0,
        last_attempt_at=None, synced_at=None, last_error=None,
        payload_json=json.dumps(integration.build_inventory_event(order_payload(), 'sale_voided')),
    )

    class FakeQuery:
        def filter(self, *_args):
            return self
        def order_by(self, *_args):
            return self
        def populate_existing(self):
            return self
        def limit(self, *_args):
            return self
        def first(self):
            return sale
        def all(self):
            return [row]

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()
        def add(self, _value):
            pass
        def commit(self):
            pass

    calls = _stub_inventory_worker(monkeypatch)
    db = FakeDb()
    waiting = asyncio.run(integration.run_inventory_outbox_sync(db))
    assert waiting['skipped'] == 1
    assert waiting['processed'] == 0
    assert row.status == 'inventory_pending'
    assert calls['posts'] == 0

    sale.status = 'synced'
    delivered = asyncio.run(integration.run_inventory_outbox_sync(db))
    assert delivered['synced'] == 1
    assert calls['posts'] == 1
    assert row.status == 'synced'


@pytest.mark.parametrize('status_code', [408, 425, 429, 503])
def test_inventory_transient_http_failures_remain_eligible_for_retry(monkeypatch, status_code):
    row = SimpleNamespace(
        id=27, aggregate_id=15, event_type='inventory.sale_completed',
        status='inventory_pending', next_retry_at=None, retry_count=0,
        last_attempt_at=None, synced_at=None, last_error=None,
        payload_json=json.dumps(integration.build_inventory_event(order_payload(), 'sale_completed')),
    )

    class FakeQuery:
        def filter(self, *_args):
            return self
        def order_by(self, *_args):
            return self
        def limit(self, *_args):
            return self
        def all(self):
            return [row]

    class FakeDb:
        def query(self, *_args):
            return FakeQuery()
        def add(self, _value):
            pass
        def commit(self):
            pass

    calls = _stub_inventory_worker(monkeypatch, response_status=status_code)
    result = asyncio.run(integration.run_inventory_outbox_sync(FakeDb()))
    assert result['retrying'] == 1
    assert result['blocked'] == 0
    assert row.status == 'inventory_retry'
    assert row.retry_count == 1
    assert row.next_retry_at is not None
    assert calls['posts'] == 1


def test_synced_inventory_sale_snapshot_is_immutable_across_duplicate_enqueue():
    db = _inventory_outbox_session()
    original = order_payload()
    sale = integration.enqueue_inventory_event(db, original, 'sale_completed', commit=False)
    original_payload = sale.payload_json
    original_id = sale.id
    sale.status = 'synced'
    sale.synced_at = '2026-10-21T10:00:00'
    db.commit()

    edited = order_payload(lines=[
        {'sku_code': 'DIFFERENT-SKU', 'quantity': 99, 'item_name_snapshot': 'Updated catalog'},
    ])
    duplicated = integration.enqueue_inventory_event(db, edited, 'sale_completed', commit=False)

    assert duplicated.id == original_id
    assert duplicated.status == 'synced'
    assert duplicated.synced_at == '2026-10-21T10:00:00'
    assert duplicated.payload_json == original_payload
    assert db.query(SyncOutboxEvent).count() == 1

    # Downstream stock return must use exactly the originally acknowledged
    # physical SKU/quantity, even if the current POS catalog was replaced.
    void = integration.enqueue_inventory_event(db, edited, 'sale_voided', commit=False)
    assert json.loads(void.payload_json)['lines'] == json.loads(original_payload)['lines']
    assert 'DIFFERENT-SKU' not in void.payload_json
    db.close()


def test_inventory_reenqueue_after_lost_ack_preserves_payload_and_retry_clock():
    db = _inventory_outbox_session()
    original = integration.enqueue_inventory_event(
        db, order_payload(), 'sale_completed', commit=False,
    )
    payload = original.payload_json
    original.status = 'inventory_retry'
    original.retry_count = 2
    original.next_retry_at = '2026-10-21T23:00:00'
    original.last_error = 'Inventory HTTP 503: acknowledgement lost'
    db.commit()

    changed = order_payload(lines=[
        {'sku_code': 'LATER-CATALOG-SKU', 'quantity': 100, 'item_name_snapshot': 'Changed after sale'},
    ])
    replay = integration.enqueue_inventory_event(db, changed, 'sale_completed', commit=False)
    assert replay.id == original.id
    assert replay.payload_json == payload
    assert replay.status == 'inventory_retry'
    assert replay.retry_count == 2
    assert replay.next_retry_at == '2026-10-21T23:00:00'
    assert replay.last_error == 'Inventory HTTP 503: acknowledgement lost'
    assert db.query(SyncOutboxEvent).count() == 1
    db.close()


def test_inventory_reenqueue_cannot_silently_reopen_blocked_snapshot():
    db = _inventory_outbox_session()
    incomplete = order_payload(lines=[
        {'catalog_item_id': 9, 'sku_code': None, 'external_sku_id': None,
         'item_name_snapshot': 'Original unmapped item', 'quantity': 1},
    ])
    original = integration.enqueue_inventory_event(db, incomplete, 'sale_completed', commit=False)
    original.status = 'blocked'
    original.last_error = 'Inventory SKU mapping requires review'
    payload = original.payload_json
    db.commit()

    changed = order_payload(lines=[
        {'sku_code': 'NEW-MAPPING', 'quantity': 1, 'item_name_snapshot': 'Mapped later'},
    ])
    repeated = integration.enqueue_inventory_event(db, changed, 'sale_completed', commit=False)
    assert repeated.status == 'blocked'
    assert repeated.last_error == 'Inventory SKU mapping requires review'
    assert repeated.payload_json == payload
    assert db.query(SyncOutboxEvent).count() == 1
    db.close()


def test_inventory_idempotency_key_collision_with_other_aggregate_fails_closed():
    db = _inventory_outbox_session()
    key = 'inventory:pos:order-uuid-15:sale_completed'
    row = SyncOutboxEvent(
        event_uuid=str(uuid.uuid4()), aggregate_type='order', aggregate_id=999,
        event_type='inventory.sale_completed', idempotency_key=key,
        payload_json='{"external_product_id":"ORIGINAL"}', status='synced',
    )
    db.add(row)
    db.commit()

    with pytest.raises(ValueError, match='idempotency key conflicts'):
        integration.enqueue_inventory_event(db, order_payload(), 'sale_completed', commit=False)
    db.rollback()
    assert db.query(SyncOutboxEvent).one().payload_json == '{"external_product_id":"ORIGINAL"}'
    db.close()
