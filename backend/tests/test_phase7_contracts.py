import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, Outlet, Register, SyncOutboxEvent, User, RoomChargePosting
from app.schemas.common import OrderCreate, OrderPayPayload, OrderPaymentCreate, RefundCreate, RegisterSessionOpen, RoomChargePostingStatusUpdate
from app.services.auth_service import hash_password
from app.services.pos_service import create_order, create_refund, open_register_session, pay_order, save_setting_json, update_room_charge_posting_status, void_order
from app.services.sync_service import _push_cash_movement, _push_order, _push_order_void, _push_payment_refund, _push_reconciliation, run_outbox_sync


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, get_map=None):
        self.get_map = get_map or {}
        self.posts = []

    async def get(self, url, params=None):
        payload = self.get_map.get((url, json.dumps(params or {}, sort_keys=True)), self.get_map.get((url, None), []))
        payload = payload(params) if callable(payload) else payload
        return FakeResponse(200, payload)

    async def post(self, url, json=None):
        self.posts.append((url, json))
        return FakeResponse(200, {'ok': True})


class ReplayAsyncClient:
    def __init__(self, *args, **kwargs):
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        if url.endswith('/cashflow/transactions'):
            return FakeResponse(200, [{'reference_no': 'CARD-REPLAY-1'}])
        if url.endswith('/menu/sales'):
            return FakeResponse(200, [])
        return FakeResponse(200, [])

    async def post(self, url, json=None):
        self.posts.append((url, json))
        return FakeResponse(200, {'ok': True})


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed(db):
    manager = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    db.add(manager); db.commit(); db.refresh(manager)
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet); db.commit(); db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    item = CatalogItem(external_menu_item_id=3001, external_sku_id=4001, menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add_all([register, item]); db.commit(); db.refresh(register); db.refresh(item)
    return manager, register, item


def test_sale_contract_maps_split_tender_to_mixed_accounting_payload():
    db = make_session()
    _manager, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', table_label='T1', lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=120, amount_received=120), OrderPaymentCreate(tender_type='card', amount_applied=80, amount_received=80, accounting_financial_account_id=9, reference_no='CARD-7788')]))
    outbox = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'order.finalized').first()
    payload = json.loads(outbox.payload_json)
    client = FakeClient({('https://acct.test/menu/sales', None): []})
    res = asyncio.run(_push_order(client, 'https://acct.test', {}, payload))
    assert res.status_code == 200
    _url, body = client.posts[0]
    assert body['payment_method'] == 'mixed'
    assert body['external_source'] == 'dedicated_pos_cloud'
    assert body['external_id'] == payload['order_uuid']
    assert body['lines'][0]['menu_item_id'] == 3001


def test_refund_contract_maps_to_outgoing_cashflow_payload():
    db = make_session()
    manager, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=100, amount_received=100, accounting_financial_account_id=12, reference_no='GC-ORIG-1')]))
    create_refund(db, order['id'], RefundCreate(refund_mode='full', reason_text='Guest changed mind', approved_by_user_id=manager.id), cashier_user_id=manager.id)
    outbox = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'payment.refunded').first()
    payload = json.loads(outbox.payload_json)
    client = FakeClient({('https://acct.test/cashflow/transactions', None): []})
    res = asyncio.run(_push_payment_refund(client, 'https://acct.test', {}, payload))
    assert res.status_code == 200
    _url, body = client.posts[0]
    assert body['direction'] == 'out'
    assert body['category'] == 'POS Refund'
    assert body['external_id'].startswith('refund-payment:')


def test_void_contract_posts_reversal_only_when_sale_exists():
    client = FakeClient({('https://acct.test/menu/sales', None): [{'id': 77, 'order_no': 'ORD-1', 'status': 'posted'}]})
    payload = {'order_no': 'ORD-1', 'business_date': '2026-04-20', 'reason': 'Customer cancelled'}
    res = asyncio.run(_push_order_void(client, 'https://acct.test', {}, payload))
    assert res.status_code == 200
    url, body = client.posts[0]
    assert url == 'https://acct.test/menu/sales/77/void'
    assert body['reverse_inventory'] is True


def test_cash_movement_and_reconciliation_contract_payloads_are_stable():
    cash_client = FakeClient({('https://acct.test/cashflow/transactions', None): []})
    cash_payload = {'event_date': '2026-04-20', 'direction': 'out', 'movement_type': 'paid_out', 'category': 'Taxi', 'amount': 150, 'reference_no': 'PO-1', 'cash_event_uuid': 'uuid-1', 'accounting_financial_account_id': 1, 'note': 'Taxi reimbursement', 'id': 10}
    asyncio.run(_push_cash_movement(cash_client, 'https://acct.test', {}, cash_payload))
    _url, body = cash_client.posts[0]
    assert body['external_id'] == 'PO-1'
    assert body['linked_record_type'] == 'pos_cash_movement'

    recon_client = FakeClient({('https://acct.test/reconciliations', None): []})
    recon_payload = {'register_accounting_financial_account_id': 1, 'business_date': '2026-04-20', 'session_code': '2026-04-20-AM-MAIN', 'closing_actual_cash': 1480, 'closing_expected_cash': 1500, 'variance_amount': -20, 'close_mode': 'verified', 'denomination_lines': [{'line_label': '20x24', 'amount': 480, 'sort_order': 1}]}
    asyncio.run(_push_reconciliation(recon_client, 'https://acct.test', {}, recon_payload))
    _url, recon_body = recon_client.posts[0]
    assert recon_body['financial_account_id'] == 1
    assert recon_body['shift_name'] == '2026-04-20-AM-MAIN'
    assert recon_body['lines'][0]['line_label'] == '20x24'


def test_duplicate_replay_marks_event_synced_without_duplicate_post(monkeypatch):
    db = make_session()
    _manager, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Replay Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='card', amount_applied=100, amount_received=100, accounting_financial_account_id=9, reference_no='CARD-REPLAY-1')]))
    save_setting_json(db, 'accounting_sync', {'api_base': 'https://acct.test', 'sync_cash_movements': True, 'sync_orders': False, 'sync_reconciliations': False})
    monkeypatch.setattr('app.services.sync_service.httpx.AsyncClient', ReplayAsyncClient)
    result = asyncio.run(run_outbox_sync(db, limit=10))
    payment_event = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'payment.collected').first()
    assert result['synced'] >= 1
    assert payment_event.status == 'synced'


def test_room_charge_pending_posted_settled_and_rejected_contract_path():
    db = make_session()
    manager, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], order_type='room_service', guest_name='Room 201', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_room_number='201', room_charge_guest_label='Rm 201 · Juan', room_charge_booking_date='2026-04-20', room_charge_service_date='2026-04-20')]))
    posting = db.query(RoomChargePosting).first()
    posted = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-201'), user_id=manager.id)
    settled = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', later_payment_status='settled', payment_date='2026-04-21'), user_id=manager.id)
    rejected = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='rejected', rejected_reason='Front desk found wrong guest'), user_id=manager.id)
    assert posted['posting_status'] == 'posted_to_beds24'
    assert settled['payment_date'] == '2026-04-21'
    assert rejected['rejected_reason'] == 'Front desk found wrong guest'
