from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, InHouseBookingSnapshot, Outlet, Register, RegisterSession, RoomChargePosting, SyncOutboxEvent
from app.schemas.common import CashMovementCreate, InHouseBookingSnapshotCreate, OrderCreate, OrderPayPayload, OrderPaymentCreate, OrderUpdate, RefundCreate, RegisterSessionOpen, RoomChargePostingStatusUpdate
from app.services.pos_service import create_cash_movement, create_in_house_booking_snapshot, create_order, create_refund, open_register_session, pay_order, set_order_status, update_order, update_room_charge_posting_status, void_order


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_register(db):
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    db.add(register)
    db.commit()
    db.refresh(register)
    return register


def seed_catalog(db):
    item = CatalogItem(menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def seed_manager(db):
    from app.models.entities import User
    from app.services.auth_service import hash_password

    user = User(username='manager1', full_name='Manager One', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_hold_resume_update_and_pay_same_order():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=500, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Caryl', table_label='T1', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    set_order_status(db, order['id'], 'held')
    set_order_status(db, order['id'], 'draft')
    updated = update_order(db, order['id'], OrderUpdate(lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=200, amount_received=200)]))
    assert updated['id'] == order['id']
    assert paid['id'] == order['id']
    assert paid['status'] == 'paid'
    assert paid['total_amount'] == 200


def test_non_cash_payment_creates_settlement_outbox():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=100, amount_received=100, accounting_financial_account_id=2, reference_no='GC-1')]))
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'payment.collected' for e in events)
    assert any(e.event_type == 'order.finalized' for e in events)


def test_void_order_creates_void_outbox():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100)]))
    voided = void_order(db, order['id'], 'Customer cancelled')
    assert voided['status'] == 'voided'
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'order.voided' for e in events)


def test_full_cash_refund_creates_cash_out_and_refund_record():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=200, amount_received=200)]))

    refund = create_refund(db, order['id'], RefundCreate(refund_mode='full', reason_code='guest_request', reason_text='Guest changed mind', approved_by_user_id=manager.id), cashier_user_id=manager.id)

    assert refund['refunded_amount'] == 200
    assert refund['approved_by_user_id'] == manager.id
    assert refund['payments'][0]['tender_type'] == 'cash'
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'cash_movement.created' for e in events)


def test_partial_line_refund_allocates_non_cash_refund_event():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=200, amount_received=200, accounting_financial_account_id=2, reference_no='GC-2')]))

    line_id = paid['lines'][0]['id']
    refund = create_refund(db, order['id'], RefundCreate(refund_mode='lines', reason_code='wrong_item', approved_by_user_id=manager.id, lines=[{'order_line_id': line_id, 'quantity': 1}]), cashier_user_id=manager.id)

    assert refund['refunded_amount'] == 100
    assert refund['lines'][0]['quantity'] == 1
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'payment.refunded' for e in events)


def test_room_charge_marks_order_as_folio_pending_and_not_paid():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 201', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))

    settled = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, reference_no='RM-201')]))

    assert settled['status'] == 'folio_pending'
    assert settled['paid_amount'] == 0
    assert settled['settled_amount'] == 0
    assert settled['folio_pending_amount'] == 100
    assert settled['balance_due'] == 0
    assert settled['payment_breakdown'][0]['settlement_state'] == 'pending_folio_post'
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'payment.folio_pending' for e in events)
    assert any(e.event_type == 'order.finalized' for e in events)


def test_mixed_cash_and_room_charge_tracks_only_immediate_settlement_as_paid_amount():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 305', lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))

    settled = pay_order(db, order['id'], OrderPayPayload(payments=[
        OrderPaymentCreate(tender_type='cash', amount_applied=50, amount_received=50),
        OrderPaymentCreate(tender_type='room_charge', amount_applied=150, reference_no='RM-305'),
    ]))

    assert settled['status'] == 'folio_pending'
    assert settled['paid_amount'] == 50
    assert settled['settled_amount'] == 50
    assert settled['folio_pending_amount'] == 150
    assert settled['balance_due'] == 0
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'cash_movement.created' for e in events)
    assert any(e.event_type == 'payment.folio_pending' for e in events)



def test_room_charge_creates_dedicated_posting_record_from_snapshot():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    snapshot = create_in_house_booking_snapshot(db, InHouseBookingSnapshotCreate(stay_date='2026-04-19', room_number='201', guest_name='Juan Dela Cruz', guest_label='Rm 201 · Juan Dela Cruz', arrival_date='2026-04-18', departure_date='2026-04-20', booking_status='in_house', beds24_booking_id='B24-201'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Juan Dela Cruz', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))

    settled = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, reference_no='RM-201', room_charge_service_type='room_service', room_charge_booking_snapshot_id=snapshot['id'])]))

    posting = db.query(RoomChargePosting).first()
    assert posting is not None
    assert posting.room_number == '201'
    assert posting.guest_label == 'Rm 201 · Juan Dela Cruz'
    assert posting.beds24_booking_id == 'B24-201'
    assert posting.posting_status == 'pending_frontdesk_post'
    assert settled['room_charge_postings'][0]['posting_status'] == 'pending_frontdesk_post'



def test_room_charge_status_updates_track_posting_and_payment_dates_separately():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 305', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_service_type='signed_from_cafe', room_charge_booking_date='2026-04-19', room_charge_service_date='2026-04-19', room_charge_room_number='305', room_charge_guest_label='Rm 305 · Maria Santos', room_charge_order_source='restaurant')]))

    posting = db.query(RoomChargePosting).first()
    posted = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-305'))
    settled = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', payment_date='2026-04-20', later_payment_status='settled'))

    assert posted['posting_status'] == 'posted_to_beds24'
    assert posted['beds24_posting_reference'] == 'INV-305'
    assert posted['posted_to_beds24_at'] is not None
    assert settled['posting_status'] == 'settled_at_frontdesk'
    assert settled['payment_date'] == '2026-04-20'
    assert settled['later_payment_status'] == 'settled'
    assert settled['settled_at_frontdesk_at'] is not None
