import asyncio
import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import sync_service


class Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else []
        self.text = json.dumps(self._body)

    def json(self):
        return self._body


class Client:
    def __init__(self, *, rows=None, lookup_status=200):
        self.rows = rows if rows is not None else []
        self.lookup_status = lookup_status
        self.posts = []
        self.gets = []

    async def get(self, url, params=None):
        self.gets.append((url, params))
        return Response(self.lookup_status, self.rows)

    async def post(self, url, json):
        self.posts.append((url, json))
        return Response(201, {'ok': True})


def refund_payload():
    return {
        'refund_no': 'RFD-42',
        'order_no': 'POS-100',
        'created_at': '2026-10-20',
        'payment': {
            'id': 42, 'tender_type': 'gcash', 'amount': 100,
            'reference_no': 'GC-ORIGINAL-123',
            'accounting_financial_account_id': 7,
        },
    }


def test_refund_is_not_silently_skipped_by_original_payment_reference():
    client = Client(rows=[{
        'reference_no': 'GC-ORIGINAL-123',
        'direction': 'in',
        'external_source': 'dedicated_pos_cloud',
        'external_id': 'GC-ORIGINAL-123',
    }])
    result = asyncio.run(sync_service._push_payment_refund(
        client, 'https://accounting.example/api', {}, refund_payload(),
    ))
    assert result.status_code == 201
    assert len(client.posts) == 1
    sent = client.posts[0][1]
    assert sent['direction'] == 'out'
    assert sent['external_id'] == 'refund-payment:42'
    assert sent['reference_no'] == 'GC-ORIGINAL-123'


def test_exact_same_accounting_refund_external_id_is_idempotent():
    client = Client(rows=[{
        'reference_no': 'GC-ORIGINAL-123',
        'direction': 'out',
        'external_source': 'dedicated_pos_cloud',
        'external_id': 'refund-payment:42',
    }])
    result = asyncio.run(sync_service._push_payment_refund(
        client, 'https://accounting.example/api', {}, refund_payload(),
    ))
    assert result is None
    assert client.posts == []


def test_accounting_review_routes_use_post_only_and_server_idempotency():
    class ReviewClient(Client):
        async def get(self, *_args, **_kwargs):
            raise AssertionError('Review Inbox endpoints must not receive GET duplicate checks.')

    client = ReviewClient()
    result = asyncio.run(sync_service._push_payment_refund(
        client, 'https://accounting.example/api',
        {'current_erp_cashflow_path': '/integrations/pos-review/cashflow'},
        refund_payload(),
    ))
    assert result.status_code == 201
    assert client.posts[0][1]['external_id'] == 'refund-payment:42'


def test_new_cash_events_use_stable_event_uuid_not_reused_paper_reference():
    client = Client()
    config = {'current_erp_cashflow_path': '/integrations/pos-review/cashflow'}
    first = {
        'id': 1, 'cash_event_uuid': str(uuid.uuid4()),
        'integration_identity_version': 2,
        'event_date': '2026-10-20', 'movement_type': 'paid_out',
        'direction': 'out', 'amount': 30,
        'reference_no': 'RECEIPT-1', 'accounting_financial_account_id': 1,
    }
    second = {**first, 'id': 2, 'cash_event_uuid': str(uuid.uuid4())}
    asyncio.run(sync_service._push_cash_movement(
        client, 'https://accounting.example/api', config, first,
    ))
    asyncio.run(sync_service._push_cash_movement(
        client, 'https://accounting.example/api', config, second,
    ))
    a, b = [body for _, body in client.posts]
    assert a['reference_no'] == b['reference_no'] == 'RECEIPT-1'
    assert a['external_id'] == f"cash-movement:{first['cash_event_uuid']}"
    assert b['external_id'] == f"cash-movement:{second['cash_event_uuid']}"
    assert a['external_id'] != b['external_id']


def test_historical_cash_event_preserves_original_external_identity():
    client = Client()
    asyncio.run(sync_service._push_cash_movement(
        client, 'https://accounting.example/api',
        {'current_erp_cashflow_path': '/integrations/pos-review/cashflow'},
        {'cash_event_uuid': str(uuid.uuid4()), 'reference_no': 'OLD-RECEIPT',
         'direction': 'in', 'amount': 20, 'accounting_financial_account_id': 1},
    ))
    assert client.posts[0][1]['external_id'] == 'OLD-RECEIPT'


def test_distinct_new_cash_transfers_with_same_reference_do_not_collapse():
    client = Client()
    config = {'current_erp_transfers_path': '/integrations/pos-review/transfer'}
    payload = {
        'cash_event_uuid': str(uuid.uuid4()),
        'integration_identity_version': 2,
        'transfer_date': '2026-10-20',
        'from_account_id': 1, 'to_account_id': 2,
        'amount': 30, 'reference_no': 'BANK-SLIP',
    }
    asyncio.run(sync_service._push_transfer(client, 'https://accounting.example/api', config, payload))
    next_payload = {**payload, 'cash_event_uuid': str(uuid.uuid4())}
    asyncio.run(sync_service._push_transfer(client, 'https://accounting.example/api', config, next_payload))
    assert len(client.posts) == 2
    assert client.posts[0][1]['external_id'] != client.posts[1][1]['external_id']


@pytest.mark.parametrize('status', [401, 404, 429, 503])
def test_failed_accounting_duplicate_lookup_never_falls_through_to_new_post(status):
    client = Client(lookup_status=status)
    with pytest.raises(RuntimeError, match='duplicate check failed'):
        asyncio.run(sync_service._push_payment_refund(
            client, 'https://accounting.example/api', {}, refund_payload(),
        ))
    assert client.posts == []


def _db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, future=True)()


def _outbox_row(event_type, event_id, *, aggregate_id=22):
    return SyncOutboxEvent(
        event_uuid=str(uuid.uuid4()),
        aggregate_type='order',
        aggregate_id=aggregate_id,
        event_type=event_type,
        idempotency_key=f'accounting-test:{event_id}',
        payload_json=json.dumps({
            'id': aggregate_id, 'order_no': 'POS-22', 'order_uuid': 'UUID-22',
            'business_date': '2026-10-20',
        }),
        status='pending',
    )


def test_manual_retry_does_not_acknowledge_void_before_original_sale():
    db = _db()
    sale = _outbox_row('order.finalized', 'sale')
    void = _outbox_row('order.voided', 'void')
    db.add_all([sale, void])
    db.commit()

    assert sync_service._accounting_void_waits_for_sale(db, void)
    result = asyncio.run(sync_service.retry_outbox_event(db, void.id))
    assert result['skipped'] is True
    assert db.get(SyncOutboxEvent, void.id).status == 'pending'
    sale.status = 'synced'
    db.commit()
    assert not sync_service._accounting_void_waits_for_sale(db, void)
    db.close()


def test_accounting_void_waits_for_failed_sale_then_delivers_after_recovery(monkeypatch):
    db = _db()
    sale = _outbox_row('order.finalized', 'sale-worker')
    void = _outbox_row('order.voided', 'void-worker')
    db.add_all([sale, void])
    db.commit()

    config = {'api_base': 'https://accounting.example/api', 'api_token': 'test-token', 'sync_orders': True}
    monkeypatch.setattr(sync_service, 'get_sync_config', lambda _db: config)

    async def ensure_token(_db, cfg):
        return cfg

    monkeypatch.setattr(sync_service, '_ensure_accounting_token', ensure_token)
    attempted = {'void': 0, 'sale_response': 503}

    async def fake_sale(*_args):
        return Response(attempted['sale_response'], {'message': 'Try again'})

    async def fake_void(*_args):
        attempted['void'] += 1
        return Response(200)

    monkeypatch.setattr(sync_service, '_push_order', fake_sale)
    monkeypatch.setattr(sync_service, '_push_order_void', fake_void)

    class AsyncClient:
        def __init__(self, **_kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(sync_service.httpx, 'AsyncClient', AsyncClient)

    first = asyncio.run(sync_service.run_outbox_sync(db, limit=10))
    assert first['failed'] == 1
    assert first['skipped'] == 1
    assert attempted['void'] == 0
    db.refresh(sale)
    db.refresh(void)
    assert sale.status == 'failed'
    assert void.status == 'pending'

    attempted['sale_response'] = 200
    sale.status = 'pending'
    sale.next_retry_at = None
    db.commit()
    second = asyncio.run(sync_service.run_outbox_sync(db, limit=10))
    assert second['synced'] == 2
    assert attempted['void'] == 1
    db.refresh(sale)
    db.refresh(void)
    assert sale.status == 'synced'
    assert void.status == 'synced'
    db.close()
