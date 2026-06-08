import asyncio
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, Outlet, Register, RoomChargePosting, SyncOutboxEvent, User
from app.schemas.common import InHouseBookingSnapshotCreate, OrderCreate, OrderPayPayload, OrderPaymentCreate, OrderUpdate, RegisterSessionClose, RegisterSessionOpen, RoomChargePostingStatusUpdate
from app.services.auth_service import hash_password
from app.services.pos_service import create_in_house_booking_snapshot, create_order, set_order_status, open_register_session, pay_order, save_setting_json, close_register_session, update_order, update_room_charge_posting_status
from app.services.sync_service import run_outbox_sync


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FlakyAsyncClient:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        return FakeResponse(200, [])

    async def post(self, url, json=None):
        FlakyAsyncClient.calls += 1
        if FlakyAsyncClient.calls == 1:
            return FakeResponse(500, {'detail': 'temporary failure'}, text='temporary failure')
        return FakeResponse(200, {'ok': True})


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed(db):
    user = User(username='cashier', full_name='Cashier', hashed_password=hash_password('secret123'), role='cashier', is_active=True)
    manager = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    db.add_all([user, manager]); db.commit(); db.refresh(user); db.refresh(manager)
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet); db.commit(); db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    item = CatalogItem(external_menu_item_id=3001, external_sku_id=4001, menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add_all([register, item]); db.commit(); db.refresh(register); db.refresh(item)
    return user, manager, register, item


def test_end_to_end_open_shift_order_room_charge_retry_sync_and_close(monkeypatch):
    db = make_session()
    cashier, manager, register, item = seed(db)

    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=500), user_id=cashier.id)
    draft = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Table 1', table_label='T1', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=cashier.id)
    set_order_status(db, draft['id'], 'held')
    set_order_status(db, draft['id'], 'draft')
    update_order(db, draft['id'], OrderUpdate(lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, draft['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=50, amount_received=50), OrderPaymentCreate(tender_type='card', amount_applied=150, amount_received=150, accounting_financial_account_id=9, reference_no='CARD-E2E-1')]), user_id=cashier.id)
    assert paid['status'] == 'paid'

    snapshot = create_in_house_booking_snapshot(db, InHouseBookingSnapshotCreate(stay_date='2026-04-20', room_number='204', guest_name='Late Checkout Guest', guest_label='Rm 204 · Late Checkout Guest'))
    room_order = create_order(db, OrderCreate(register_session_id=session['id'], order_type='room_service', guest_name='Rm 204', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=cashier.id)
    room_paid = pay_order(db, room_order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_booking_snapshot_id=snapshot['id'])]), user_id=cashier.id)
    assert room_paid['status'] == 'folio_pending'
    posting = db.query(RoomChargePosting).first()
    posted = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-E2E-204'), user_id=manager.id)
    settled = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', later_payment_status='settled', payment_date='2026-04-21'), user_id=manager.id)
    assert posted['posting_status'] == 'posted_to_beds24'
    assert settled['payment_date'] == '2026-04-21'

    save_setting_json(db, 'accounting_sync', {'api_base': 'https://acct.test', 'sync_cash_movements': True, 'sync_orders': True, 'sync_reconciliations': True})
    monkeypatch.setattr('app.services.sync_service.httpx.AsyncClient', FlakyAsyncClient)
    first = asyncio.run(run_outbox_sync(db, limit=20))
    second = asyncio.run(run_outbox_sync(db, limit=20))
    assert first['failed'] >= 1
    assert second['processed'] == 0
    failed_rows = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.status == 'failed').all()
    assert failed_rows
    for row in failed_rows:
        row.next_retry_at = '2026-04-20T00:00:00'
        db.add(row)
    db.commit()
    third = asyncio.run(run_outbox_sync(db, limit=20))
    assert third['synced'] >= 1
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.status == 'synced').count() >= 1

    closed = close_register_session(db, session['id'], RegisterSessionClose(closing_actual_cash=550, close_mode='verified', blind_close=False, sign_off_name='Cashier', sign_off_role='Cashier'))
    assert closed['status'] == 'closed'
