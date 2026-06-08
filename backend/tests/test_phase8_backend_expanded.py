import asyncio
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, ManagerApproval, Outlet, Register, RoomChargePosting, SyncOutboxEvent, User
from app.schemas.common import CashMovementCreate, CatalogItemUpdate, InHouseBookingSnapshotCreate, OrderCreate, OrderPayPayload, OrderPaymentCreate, RefundCreate, RegisterSessionClose, RegisterSessionOpen, RegisterSessionReopen, RoomChargePostingStatusUpdate
from app.services.auth_service import hash_password
from app.services.pos_service import close_register_session, create_cash_movement, create_in_house_booking_snapshot, create_order, create_refund, list_room_charge_postings, open_register_session, pay_order, reopen_register_session, update_catalog_item, update_room_charge_posting_status, save_setting_json
from app.services.sync_service import sync_catalog_from_accounting


class DummyResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = json.dumps(data)

    def json(self):
        return self._data


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, params=None):
        if url.endswith('/menu/items'):
            return DummyResponse([
                {'id': 101, 'name': 'Club Sandwich', 'category': 'Meals', 'module_slug': 'restaurant', 'price': 240, 'updated_at': '2026-04-20T12:00:00Z', 'is_active': True},
                {'id': 102, 'name': 'Iced Coffee', 'category': 'Beverages', 'module_slug': 'restaurant', 'price': 120, 'updated_at': '2026-04-20T12:00:00Z', 'is_active': True},
            ])
        if url.endswith('/menu/skus'):
            return DummyResponse([
                {'id': 201, 'menu_item_id': 102, 'sku_code': 'DRINK-001', 'variant_name': 'Regular', 'price': 120, 'updated_at': '2026-04-20T12:00:00Z', 'is_active': True},
            ])
        return DummyResponse([], 404)


def test_sync_catalog_from_accounting_imports_items_with_and_without_skus(monkeypatch):
    db = make_session()
    save_setting_json(db, 'accounting_sync', {
        'api_base': 'http://127.0.0.1/api',
        'catalog_items_path': '/menu/items',
        'catalog_skus_path': '/menu/skus',
    }, username='test')
    monkeypatch.setattr('app.services.sync_service.httpx.AsyncClient', DummyAsyncClient)
    result = asyncio.run(sync_catalog_from_accounting(db))
    assert result['ok'] is True
    assert result['menu_items_seen'] == 2
    assert result['skus_seen'] == 1
    items = db.query(CatalogItem).order_by(CatalogItem.external_menu_item_id.asc(), CatalogItem.external_sku_id.asc()).all()
    assert len(items) == 2
    simple_item = next((item for item in items if item.external_sku_id is None), None)
    variant_item = next((item for item in items if item.external_sku_id is not None), None)
    assert simple_item is not None
    assert simple_item.external_menu_item_id == 101
    assert simple_item.display_name == 'Club Sandwich'
    assert simple_item.menu_item_name == 'Club Sandwich'
    assert simple_item.category_name == 'Meals'
    assert simple_item.module_slug == 'restaurant'
    assert simple_item.prep_station == 'kitchen'
    assert variant_item is not None
    assert variant_item.external_menu_item_id == 102
    assert variant_item.external_sku_id == 201
    assert variant_item.variant_name == 'Regular'
    assert variant_item.category_name == 'Beverages'
    assert variant_item.module_slug == 'restaurant'
    assert variant_item.prep_station == 'kitchen'

    update_catalog_item(db, simple_item.id, CatalogItemUpdate(is_available=False))
    asyncio.run(sync_catalog_from_accounting(db))
    db.refresh(simple_item)
    assert simple_item.is_available is False
    assert simple_item.availability_override is False


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed(db):
    manager = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    cashier = User(username='cashier', full_name='Cashier', hashed_password=hash_password('secret123'), role='cashier', is_active=True)
    db.add_all([manager, cashier]); db.commit(); db.refresh(manager); db.refresh(cashier)
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet); db.commit(); db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    item = CatalogItem(external_menu_item_id=3001, external_sku_id=4001, menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add_all([register, item]); db.commit(); db.refresh(register); db.refresh(item)
    return manager, cashier, register, item


def test_partial_refund_on_split_tender_allocates_back_to_original_tenders():
    db = make_session()
    manager, _cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=50, amount_received=50), OrderPaymentCreate(tender_type='gcash', amount_applied=150, amount_received=150, accounting_financial_account_id=12, reference_no='GC-1')]))
    refund = create_refund(db, order['id'], RefundCreate(refund_mode='amount', amount=100, approved_by_user_id=manager.id), cashier_user_id=manager.id)
    assert refund['refunded_amount'] == 100
    tender_types = {row['tender_type'] for row in refund['payments']}
    assert tender_types == {'cash', 'gcash'}


def test_manager_override_records_discount_and_reopen_approval_rows():
    db = make_session()
    manager, cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=200), user_id=cashier.id)
    create_order(db, OrderCreate(register_session_id=session['id'], approved_by_user_id=manager.id, lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 20}]), user_id=cashier.id)
    close_register_session(db, session['id'], RegisterSessionClose(closing_actual_cash=200, sign_off_name='Closer', sign_off_role='Cashier'))
    reopen_register_session(db, session['id'], RegisterSessionReopen(reason='Wrong close', approved_by_user_id=manager.id, note='Need another sale'), user_id=cashier.id, approved_by_user_id=manager.id)
    approval_types = {row.approval_type for row in db.query(ManagerApproval).all()}
    assert 'discount' in approval_types
    assert 'reopen_session' in approval_types


def test_room_charge_queue_flow_lists_pending_and_rejected_rows():
    db = make_session()
    manager, cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0), user_id=cashier.id)
    snapshot = create_in_house_booking_snapshot(db, InHouseBookingSnapshotCreate(stay_date='2026-04-20', room_number='201', guest_name='Juan', guest_label='Rm 201 · Juan'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Juan', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=cashier.id)
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_booking_snapshot_id=snapshot['id'])]), user_id=cashier.id)
    posting = db.query(RoomChargePosting).first()
    pending = list_room_charge_postings(db, posting_status='pending_frontdesk_post')
    update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='rejected', rejected_reason='Guest already checked out'), user_id=manager.id)
    rejected = list_room_charge_postings(db, posting_status='rejected')
    assert len(pending) == 1
    assert rejected[0]['rejected_reason'] == 'Guest already checked out'


def test_posted_to_beds24_confirmation_and_later_settlement_preserve_service_date():
    db = make_session()
    manager, cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0), user_id=cashier.id)
    order = create_order(db, OrderCreate(register_session_id=session['id'], order_type='room_service', guest_name='Room 203', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=cashier.id)
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_room_number='203', room_charge_guest_label='Rm 203 · Ana', room_charge_booking_date='2026-04-20', room_charge_service_date='2026-04-20')]), user_id=cashier.id)
    posting = db.query(RoomChargePosting).first()
    posted = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-203'), user_id=manager.id)
    settled = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', later_payment_status='settled', payment_date='2026-04-22'), user_id=manager.id)
    assert posted['service_date'] == '2026-04-20'
    assert settled['payment_date'] == '2026-04-22'
    assert settled['service_date'] == '2026-04-20'


def test_transfer_semantics_safe_drop_and_bank_deposit_emit_sync_events():
    db = make_session()
    _manager, _cashier, register, _item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=1000))
    create_cash_movement(db, CashMovementCreate(register_session_id=session['id'], direction='out', movement_type='safe_drop', category='Safe Drop', amount=300, to_accounting_financial_account_id=7, approved_by_user_id=1), approved_by_user_id=1)
    create_cash_movement(db, CashMovementCreate(register_session_id=session['id'], direction='out', movement_type='bank_deposit', category='Bank Deposit', amount=400, to_accounting_financial_account_id=8, approved_by_user_id=1), approved_by_user_id=1)
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'transfer.created').count() == 2
