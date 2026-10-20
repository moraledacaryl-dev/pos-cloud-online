import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.services.pos_service as pos_service
from app.db.database import Base
from app.models.entities import (
    AuditLog,
    CashMovement,
    CatalogItem,
    Outlet,
    PosOrder,
    Register,
    RoomChargePosting,
    SyncOutboxEvent,
)
from app.schemas.common import (
    CashMovementCreate,
    CatalogItemUpdate,
    InHouseBookingSnapshotCreate,
    OrderCreate,
    OrderPaymentCreate,
    OrderPayPayload,
    OrderUpdate,
    RefundCreate,
    RegisterSessionOpen,
    RoomChargePostingStatusUpdate,
)
from app.services.pos_service import (
    create_cash_movement,
    create_in_house_booking_snapshot,
    create_order,
    create_outbox_event,
    create_refund,
    list_kitchen_lines,
    merge_order_table,
    open_register_session,
    pay_order,
    set_order_status,
    transfer_order_table,
    update_catalog_item,
    update_order,
    update_room_charge_posting_status,
    void_order,
)


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


def seed_table_order(db, session_id, item_id, table_label, *, guest_name='Guest', status='draft', service_area='Lobby', seat_count=None):
    order = create_order(db, OrderCreate(
        register_session_id=session_id,
        guest_name=guest_name,
        service_area=service_area,
        table_label=table_label,
        seat_count=seat_count,
        lines=[{'catalog_item_id': item_id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}],
    ))
    row = db.get(PosOrder, order['id'])
    row.status = status
    db.add(row)
    db.commit()
    return order


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
    assert order['created_at'].endswith('Z')
    assert paid['updated_at'].endswith('Z')


def test_strict_environment_rejects_order_on_stale_business_date(monkeypatch):
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    monkeypatch.setattr(pos_service.settings, 'environment', 'staging')
    monkeypatch.setattr(pos_service, 'today_iso', lambda: '2026-09-03')
    session = open_register_session(
        db,
        RegisterSessionOpen(register_id=register.id, business_date='2026-09-02', shift_name='AM', opening_float=0),
    )

    assert session['is_stale'] is True
    assert session['session_age_days'] >= 1
    with pytest.raises(ValueError, match='session is stale'):
        create_order(
            db,
            OrderCreate(
                register_session_id=session['id'],
                lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}],
            ),
        )


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
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100)]))
    voided = void_order(db, order['id'], 'Customer cancelled', user_id=manager.id, approved_by_user_id=manager.id)
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
    assert db.get(PosOrder, order['id']).kitchen_status == 'voided'
    assert list_kitchen_lines(db, station='kitchen') == []
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
    kitchen_rows = list_kitchen_lines(db, station='kitchen')
    assert kitchen_rows[0]['quantity'] == 1
    assert kitchen_rows[0]['refunded_quantity'] == 1
    events = db.query(SyncOutboxEvent).all()
    assert any(e.event_type == 'payment.refunded' for e in events)



def test_duplicate_refund_lines_cannot_exceed_original_quantity():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 2, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=200, amount_received=200, accounting_financial_account_id=2, reference_no='GC-3')]))
    line_id = paid['lines'][0]['id']

    with pytest.raises(ValueError, match='quantity'):
        create_refund(db, order['id'], RefundCreate(
            refund_mode='lines', reason_code='wrong_item', approved_by_user_id=manager.id,
            lines=[{'order_line_id': line_id, 'quantity': 2}, {'order_line_id': line_id, 'quantity': 1}],
        ), cashier_user_id=manager.id)

    assert list_kitchen_lines(db, station='kitchen')[0]['quantity'] == 2


def test_duplicate_refund_lines_within_quantity_leave_correct_kitchen_balance():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 3, 'unit_price': 100, 'discount_amount': 0}]))
    paid = pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=300, amount_received=300, accounting_financial_account_id=2, reference_no='GC-4')]))
    line_id = paid['lines'][0]['id']
    refund = create_refund(db, order['id'], RefundCreate(
        refund_mode='lines', reason_code='wrong_item', approved_by_user_id=manager.id,
        lines=[{'order_line_id': line_id, 'quantity': 1}, {'order_line_id': line_id, 'quantity': 1}],
    ), cashier_user_id=manager.id)

    assert refund['refunded_amount'] == 200
    kitchen_rows = list_kitchen_lines(db, station='kitchen')
    assert len(kitchen_rows) == 1
    assert kitchen_rows[0]['quantity'] == 1
    assert kitchen_rows[0]['refunded_quantity'] == 2



def test_deferred_refund_can_rollback_financial_and_accounting_outbox_changes():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='gcash', amount_applied=100, amount_received=100, accounting_financial_account_id=2, reference_no='GC-ROLLBACK')]))
    before_events = db.query(SyncOutboxEvent).count()
    # A deferred refund must never invoke Session.commit internally.
    original_commit = db.commit
    def reject_early_commit():
        raise AssertionError('Deferred refund unexpectedly committed the transaction')
    db.commit = reject_early_commit

    refund = create_refund(db, order['id'], RefundCreate(
        refund_mode='lines', reason_code='wrong_item', approved_by_user_id=manager.id,
        lines=[{'order_line_id': order['lines'][0]['id'], 'quantity': 1}],
    ), cashier_user_id=manager.id, commit=False)
    assert refund['refunded_amount'] == 100
    assert db.query(SyncOutboxEvent).count() > before_events

    db.commit = original_commit
    db.rollback()
    db.expire_all()
    assert db.query(pos_service.Refund).filter(pos_service.Refund.order_id == order['id']).count() == 0
    assert db.query(SyncOutboxEvent).count() == before_events



def test_full_amount_refund_removes_order_from_active_kitchen_queue():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(
        db,
        RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'),
    )
    order = create_order(
        db,
        OrderCreate(
            register_session_id=session['id'],
            guest_name='Guest',
            lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}],
        ),
    )
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100)]))

    create_refund(
        db,
        order['id'],
        RefundCreate(refund_mode='amount', amount=100, reason_code='guest_request', approved_by_user_id=manager.id),
        cashier_user_id=manager.id,
    )

    assert db.get(PosOrder, order['id']).kitchen_status == 'voided'
    assert list_kitchen_lines(db, station='kitchen') == []


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
    assert not any(e.event_type == 'payment.folio_pending' for e in events)
    assert sum(e.event_type == 'room_charge.request_created' for e in events) == 1
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
    assert not any(e.event_type == 'payment.folio_pending' for e in events)
    assert sum(e.event_type == 'room_charge.request_created' for e in events) == 1



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


def test_room_charge_refund_creates_reversal_posting_and_outbox_event():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 207', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_booking_date='2026-04-19', room_charge_service_date='2026-04-19', room_charge_room_number='207', room_charge_guest_label='Rm 207 Test Guest')]))

    refund = create_refund(db, order['id'], RefundCreate(refund_mode='full', reason_code='guest_request', reason_text='Guest adjustment', approved_by_user_id=manager.id), cashier_user_id=manager.id)

    postings = db.query(RoomChargePosting).order_by(RoomChargePosting.id.asc()).all()
    assert refund['refunded_amount'] == 100
    assert len(postings) == 2
    original, reversal = postings
    assert reversal.order_payment_id is None
    assert reversal.charge_amount == -100
    assert reversal.booking_date == original.booking_date == '2026-04-19'
    assert reversal.service_date == original.service_date == '2026-04-19'
    event = db.query(SyncOutboxEvent).filter(SyncOutboxEvent.aggregate_type == 'room_charge_posting', SyncOutboxEvent.aggregate_id == reversal.id, SyncOutboxEvent.event_type == 'room_charge.request_created').one()
    event_payload = json.loads(event.payload_json)
    assert event_payload['room_charge_posting']['charge_amount'] == -100
    assert event_payload['reverses_source_type'] == 'pos_room_charge'
    assert event_payload['reverses_source_id'] == original.id


def test_synced_catalog_items_only_allow_local_availability_override():
    db = make_session()
    item = CatalogItem(external_menu_item_id=11, external_sku_id=22, menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add(item)
    db.commit()
    db.refresh(item)

    sold_out = update_catalog_item(db, item.id, CatalogItemUpdate(is_available=False))
    assert sold_out['is_available'] is False
    assert sold_out['availability_override'] is False

    restored = update_catalog_item(db, item.id, CatalogItemUpdate(is_available=True))
    assert restored['is_available'] is True
    assert restored['availability_override'] is None

    try:
        update_catalog_item(db, item.id, CatalogItemUpdate(price=150))
        assert False, 'synced catalog price edit should fail'
    except ValueError as exc:
        assert 'Inventory owns synced catalog details' in str(exc)


def test_table_transfer_and_merge_are_atomic_backend_operations():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    source = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Source', table_label='T1', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    target = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Target', table_label='T2', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))

    manager = seed_manager(db)

    transferred = transfer_order_table(db, source['id'], 'T3', user_id=manager.id)
    assert transferred['table_label'] == 'T3'

    merged = merge_order_table(db, source['id'], 'T2', user_id=manager.id)
    assert merged['id'] == target['id']
    assert len(merged['lines']) == 2
    assert merged['total_amount'] == 200
    source_row = db.get(PosOrder, source['id'])
    assert source_row.status == 'merged'
    assert source_row.kitchen_status == 'merged'
    assert source_row.void_reason is None
    assert 'Merged into' in (source_row.note or '')
    audits = {row.action: row for row in db.query(AuditLog).filter(AuditLog.action.in_(['order.table_transferred', 'order.table_merged'])).all()}
    assert audits['order.table_transferred'].actor_user_id == manager.id
    assert audits['order.table_merged'].actor_user_id == manager.id


def test_table_transfer_blocks_all_active_target_statuses():
    active_statuses = ['draft', 'held', 'open', 'sent', 'served', 'unpaid']
    for status in active_statuses:
        db = make_session()
        register = seed_register(db)
        item = seed_catalog(db)
        session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name=f'AM-{status}', opening_float=0, opening_note='open'))
        source = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Source')
        seed_table_order(db, session['id'], item.id, 'T2', guest_name='Target', status=status)

        with pytest.raises(ValueError, match='already has an active order'):
            transfer_order_table(db, source['id'], 'T2')


def test_table_transfer_allows_inactive_target_statuses():
    inactive_statuses = ['paid', 'voided', 'cancelled', 'refunded', 'merged', 'closed', 'folio_pending']
    for status in inactive_statuses:
        db = make_session()
        register = seed_register(db)
        item = seed_catalog(db)
        session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name=f'PM-{status}', opening_float=0, opening_note='open'))
        source = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Source')
        seed_table_order(db, session['id'], item.id, 'T2', guest_name='Inactive Target', status=status)

        transferred = transfer_order_table(db, source['id'], 'T2')
        assert transferred['table_label'] == 'T2'


def test_table_merge_uses_same_active_status_matrix_as_frontend():
    active_statuses = ['draft', 'held', 'open', 'sent', 'served', 'unpaid']
    for status in active_statuses:
        db = make_session()
        register = seed_register(db)
        item = seed_catalog(db)
        session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name=f'MG-{status}', opening_float=0, opening_note='open'))
        source = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Source', status='sent')
        target = seed_table_order(db, session['id'], item.id, 'T2', guest_name='Target', status=status)

        merged = merge_order_table(db, source['id'], 'T2')
        assert merged['id'] == target['id']
        assert len(merged['lines']) == 2
        assert db.get(PosOrder, source['id']).status == 'merged'

    inactive_statuses = ['paid', 'voided', 'cancelled', 'refunded', 'merged', 'closed', 'folio_pending']
    for status in inactive_statuses:
        db = make_session()
        register = seed_register(db)
        item = seed_catalog(db)
        session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name=f'MG-NO-{status}', opening_float=0, opening_note='open'))
        source = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Source')
        seed_table_order(db, session['id'], item.id, 'T2', guest_name='Inactive Target', status=status)

        with pytest.raises(ValueError, match='does not have an active order'):
            merge_order_table(db, source['id'], 'T2')



def test_room_charge_status_updates_track_posting_and_payment_dates_separately():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 305', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]))
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_service_type='signed_from_cafe', room_charge_booking_date='2026-04-19', room_charge_service_date='2026-04-19', room_charge_room_number='305', room_charge_guest_label='Rm 305 · Maria Santos', room_charge_order_source='restaurant')]))

    posting = db.query(RoomChargePosting).first()
    posted = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-305', payment_date='2026-04-20', later_payment_status='settled'))
    posted_row = db.get(RoomChargePosting, posting.id)

    assert posted['posting_status'] == 'posted_to_beds24'
    assert posted['beds24_posting_reference'] == 'INV-305'
    assert posted['posted_to_beds24_at'] is not None
    assert posted['payment_date'] is None
    assert posted_row.payment_date is None
    assert posted_row.later_payment_status == 'pending'

    settled = update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', payment_date='2026-04-20', later_payment_status='settled'))
    assert settled['posting_status'] == 'settled_at_frontdesk'
    assert settled['payment_date'] == '2026-04-20'
    assert settled['later_payment_status'] == 'settled'
    assert settled['settled_at_frontdesk_at'] is not None


def test_create_outbox_event_does_not_commit_inside_larger_workflow():
    db = make_session()
    create_outbox_event(db, aggregate_type='order', aggregate_id=123, event_type='order.test', payload={'ok': True})
    assert db.query(SyncOutboxEvent).count() == 1
    db.rollback()
    assert db.query(SyncOutboxEvent).count() == 0


def test_local_only_order_outbox_is_suppressed_instead_of_blocked():
    db = make_session()
    row = create_outbox_event(
        db,
        aggregate_type='order',
        aggregate_id=124,
        event_type='order.finalized',
        payload={'lines': [{'item_name_snapshot': 'OPERATIONAL TEST', 'external_menu_item_id': None}]},
    )

    assert row.status == 'suppressed'
    assert 'POS-local catalog line' in row.last_error


def test_discount_order_rolls_back_if_approval_record_fails(monkeypatch):
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))

    def fail_approval(*_args, **_kwargs):
        raise RuntimeError('approval store unavailable')

    monkeypatch.setattr(pos_service, 'create_manager_approval', fail_approval)
    with pytest.raises(ValueError, match='Manager approval could not be recorded'):
        create_order(db, OrderCreate(register_session_id=session['id'], approved_by_user_id=manager.id, guest_name='Discount Guest', service_area='Lobby', table_label='L1', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 10}]), user_id=manager.id)
    db.rollback()
    assert db.query(PosOrder).count() == 0


def test_void_order_does_not_commit_if_approval_record_fails(monkeypatch):
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Void Guest', service_area='Lobby', table_label='L1', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=manager.id)

    def fail_approval(*_args, **_kwargs):
        raise RuntimeError('approval store unavailable')

    monkeypatch.setattr(pos_service, 'create_manager_approval', fail_approval)
    with pytest.raises(ValueError, match='Manager approval could not be recorded'):
        void_order(db, order['id'], 'test failure', user_id=manager.id, approved_by_user_id=manager.id)
    db.rollback()
    assert db.get(PosOrder, order['id']).status == 'draft'


def test_room_charge_write_off_does_not_commit_if_approval_record_fails(monkeypatch):
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Room 301', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=manager.id)
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_room_number='301', room_charge_guest_label='Rm 301 · Guest')]), user_id=manager.id)
    posting = db.query(RoomChargePosting).first()
    update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-301'), user_id=manager.id)

    def fail_approval(*_args, **_kwargs):
        raise RuntimeError('approval store unavailable')

    monkeypatch.setattr(pos_service, 'create_manager_approval', fail_approval)
    with pytest.raises(ValueError, match='Manager approval could not be recorded'):
        update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='written_off', note='test failure'), user_id=manager.id, approved_by_user_id=manager.id)
    db.rollback()
    assert db.get(RoomChargePosting, posting.id).posting_status == 'posted_to_beds24'


def test_cash_paid_out_does_not_commit_if_approval_record_fails(monkeypatch):
    db = make_session()
    register = seed_register(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=500, opening_note='open'))

    def fail_approval(*_args, **_kwargs):
        raise RuntimeError('approval store unavailable')

    monkeypatch.setattr(pos_service, 'create_manager_approval', fail_approval)
    with pytest.raises(ValueError, match='Manager approval could not be recorded'):
        create_cash_movement(db, CashMovementCreate(register_session_id=session['id'], direction='out', movement_type='paid_out', category='Emergency Purchase', amount=25, approved_by_user_id=manager.id), approved_by_user_id=manager.id)
    db.rollback()
    assert db.query(CashMovement).count() == 1  # opening float remains, paid-out was not committed
    assert not db.query(CashMovement).filter(CashMovement.movement_type == 'paid_out').first()


def test_merge_blocks_partially_paid_source_order():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    source = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Source', service_area='Lobby')
    seed_table_order(db, session['id'], item.id, 'T2', guest_name='Target', service_area='Lobby')
    source_row = db.get(PosOrder, source['id'])
    source_row.paid_amount = 10
    source_row.status = 'unpaid'
    db.add(source_row)
    db.commit()

    with pytest.raises(ValueError, match='Partially paid orders cannot be merged'):
        merge_order_table(db, source['id'], 'T2', target_service_area='Lobby')


def test_merge_adds_pax_and_preserves_source_guest_in_note():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    source = seed_table_order(db, session['id'], item.id, 'G1', guest_name='Garcia Family', service_area='Garden', seat_count=3)
    target = seed_table_order(db, session['id'], item.id, 'G2', guest_name='Target', service_area='Garden', seat_count=2)

    merged = merge_order_table(db, source['id'], 'G2', target_service_area='Garden')

    assert merged['id'] == target['id']
    assert merged['seat_count'] == 5
    assert 'Garcia Family' in (merged['note'] or '')
    assert 'Pax: 3' in (merged['note'] or '')


def test_transfer_and_merge_use_service_area_with_duplicate_table_codes():
    db = make_session()
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0, opening_note='open'))
    lobby_target = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Lobby Target', service_area='Lobby')
    garden_target = seed_table_order(db, session['id'], item.id, 'T1', guest_name='Garden Target', service_area='Garden')
    source = seed_table_order(db, session['id'], item.id, 'T2', guest_name='Garden Source', service_area='Garden')

    merged = merge_order_table(db, source['id'], 'T1', target_service_area='Garden')
    assert merged['id'] == garden_target['id']
    assert merged['id'] != lobby_target['id']

    transfer_source = seed_table_order(db, session['id'], item.id, 'T3', guest_name='Transfer Source', service_area='Lobby')
    transferred = transfer_order_table(db, transfer_source['id'], 'T2', target_service_area='Garden')
    assert transferred['service_area'] == 'Garden'
    assert transferred['table_label'] == 'T2'


def test_checkout_enforces_generic_conditional_price_and_legacy_fallback():
    from app.models.entities import SystemSetting
    db = make_session()
    register = seed_register(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0))
    drink = CatalogItem(menu_item_name='Drink', display_name='Drink', category_name='Cafe', module_slug='cafe', prep_station='bar', price=50, pricing_role='drink', pricing_tags_json='["qualifier"]', is_active=True, is_available=True)
    pastry = CatalogItem(menu_item_name='Pastry', display_name='Pastry', category_name='Cafe', module_slug='cafe', prep_station='kitchen', price=100, with_drink_price=90, pricing_role='pastry', pricing_tags_json='["target"]', conditional_prices_json='[{"rule_id":"combo","price":"80"}]', is_active=True, is_available=True)
    legacy = CatalogItem(menu_item_name='Legacy', display_name='Legacy', category_name='Cafe', module_slug='cafe', prep_station='kitchen', price=100, with_drink_price=90, pricing_role='pastry', pricing_tags_json='[]', conditional_prices_json='[]', is_active=True, is_available=True)
    db.add_all([drink, pastry, legacy, SystemSetting(key='catalog_sync', value_json=json.dumps({'pricing_rules':[{'id':'combo','qualifier_tag':'qualifier','target_tag':'target','priority':100}]}))])
    db.commit()
    lines = [{'catalog_item_id': drink.id, 'quantity': 1, 'unit_price': 50}, {'catalog_item_id': pastry.id, 'quantity': 1, 'unit_price': 80}, {'catalog_item_id': legacy.id, 'quantity': 1, 'unit_price': 90}]
    order = create_order(db, OrderCreate(register_session_id=session['id'], lines=lines))
    assert sum(float(line.unit_price) * float(line.quantity) for line in db.get(PosOrder, order['id']).lines) == 220
    with pytest.raises(ValueError, match='price does not match'):
        create_order(db, OrderCreate(register_session_id=session['id'], lines=[{**lines[1], 'unit_price': 70}, lines[0]]))
    db.close()


def test_unavailable_qualifier_cannot_trigger_generic_checkout_discount():
    from app.models.entities import SystemSetting
    db = make_session()
    register = seed_register(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-19', shift_name='AM', opening_float=0))
    qualifier = CatalogItem(menu_item_name='Unavailable drink', display_name='Unavailable drink', category_name='Cafe', module_slug='cafe', prep_station='bar', price=50, pricing_tags_json='["qualifier"]', is_active=True, is_available=False)
    target = CatalogItem(menu_item_name='Target', display_name='Target', category_name='Cafe', module_slug='cafe', prep_station='kitchen', price=100, pricing_tags_json='["target"]', conditional_prices_json='[{"rule_id":"combo","price":"80"}]', is_active=True, is_available=True)
    db.add_all([qualifier, target, SystemSetting(key='catalog_sync', value_json=json.dumps({'pricing_rules':[{'id':'combo','qualifier_tag':'qualifier','target_tag':'target'}]}))])
    db.commit()
    lines = [{'catalog_item_id': qualifier.id, 'quantity': 1, 'unit_price': 50}, {'catalog_item_id': target.id, 'quantity': 1, 'unit_price': 80}]
    with pytest.raises(ValueError, match='price does not match'):
        create_order(db, OrderCreate(register_session_id=session['id'], lines=lines))
    db.close()


def _seed_atomic_checkout_order(db):
    register = seed_register(db)
    item = seed_catalog(db)
    session = open_register_session(db, RegisterSessionOpen(
        register_id=register.id, business_date='2026-04-19', shift_name='AM',
        opening_float=0, opening_note='open',
    ))
    order = create_order(db, OrderCreate(
        register_session_id=session['id'], guest_name='Atomic checkout test',
        lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}],
    ))
    return order


def _assert_atomic_checkout_not_settled(db, order_id):
    db.expire_all()
    order = db.get(PosOrder, order_id)
    assert order.status == 'draft'
    assert not order.payments
    assert db.query(CashMovement).filter(CashMovement.source_order_id == order_id).count() == 0
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.aggregate_type == 'order', SyncOutboxEvent.aggregate_id == order_id).count() == 0
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'cash_movement.created').count() == 0


def test_atomic_checkout_rolls_back_deferred_settlement(monkeypatch):
    db = make_session()
    order = _seed_atomic_checkout_order(db)
    published = []
    monkeypatch.setattr(pos_service, '_publish_kds_refresh', lambda *args, **kwargs: published.append((args, kwargs)))

    staged = pay_order(db, order['id'], OrderPayPayload(payments=[
        OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100),
    ]), commit=False)
    assert staged['status'] == 'paid'
    assert db.query(CashMovement).filter(CashMovement.source_order_id == order['id']).count() == 1
    assert published == []  # A rolled-back sale must never appear on the kitchen display.
    db.rollback()

    _assert_atomic_checkout_not_settled(db, order['id'])
    assert published == []
    db.close()


def test_atomic_checkout_rolls_back_if_inventory_enqueue_fails(monkeypatch):
    from types import SimpleNamespace

    import app.api.orders as orders_api

    db = make_session()
    order = _seed_atomic_checkout_order(db)
    published = []
    monkeypatch.setattr(pos_service, '_publish_kds_refresh', lambda *args, **kwargs: published.append(True))

    def fail_inventory(*args, **kwargs):
        raise RuntimeError('Injected Inventory event failure')

    monkeypatch.setattr(orders_api, 'enqueue_inventory_event', fail_inventory)
    with pytest.raises(RuntimeError, match='Injected Inventory event failure'):
        orders_api.settle_order(
            order['id'],
            OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100)]),
            db=db, current_user=SimpleNamespace(id=None),
        )

    _assert_atomic_checkout_not_settled(db, order['id'])
    assert published == []
    db.close()


def test_atomic_checkout_rolls_back_if_operations_enqueue_fails(monkeypatch):
    from types import SimpleNamespace

    import app.api.orders as orders_api

    db = make_session()
    order = _seed_atomic_checkout_order(db)

    def fail_operations(*args, **kwargs):
        raise RuntimeError('Injected Operations event failure')

    monkeypatch.setattr(orders_api, 'enqueue_operations_event', fail_operations)
    with pytest.raises(RuntimeError, match='Injected Operations event failure'):
        orders_api.settle_order(
            order['id'],
            OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=100, amount_received=100)]),
            db=db, current_user=SimpleNamespace(id=None),
        )

    _assert_atomic_checkout_not_settled(db, order['id'])
    db.close()


def test_atomic_checkout_commits_once_then_notifies_kitchen_and_blocks_replay(monkeypatch):
    from types import SimpleNamespace

    from fastapi import HTTPException

    import app.api.orders as orders_api

    db = make_session()
    order = _seed_atomic_checkout_order(db)
    notifications = []
    commits = []
    original_commit = db.commit

    def counted_commit():
        commits.append(True)
        original_commit()

    def kitchen_notify(stations, reason, payload):
        notifications.append((stations, reason, payload, db.get(PosOrder, order['id']).status,
                              db.query(CashMovement).filter(CashMovement.source_order_id == order['id']).count()))

    monkeypatch.setattr(db, 'commit', counted_commit)
    monkeypatch.setattr(pos_service, '_publish_kds_refresh', kitchen_notify)
    monkeypatch.setattr(orders_api.enqueue_operations_event.__globals__['settings'], 'operations_integration_enabled', True)

    payment = OrderPayPayload(payments=[
        OrderPaymentCreate(tender_type='cash', amount_applied=50, amount_received=50),
        OrderPaymentCreate(tender_type='gcash', amount_applied=50, amount_received=50,
                           accounting_financial_account_id=2, reference_no='GC-ATOMIC-1'),
    ])
    result = orders_api.settle_order(order['id'], payment, db=db, current_user=SimpleNamespace(id=None))
    assert result['status'] == 'paid'
    assert len(commits) == 1
    assert len(notifications) == 1
    assert notifications[0][1] == 'ticket_finalized'
    assert notifications[0][3:] == ('paid', 1)
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'inventory.sale_completed').count() == 1
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'operations.v2.order.finalized').count() == 1
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'payment.collected').count() == 1
    with pytest.raises(HTTPException) as blocked:
        orders_api.settle_order(order['id'], payment, db=db, current_user=SimpleNamespace(id=None))
    assert blocked.value.status_code == 400
    assert db.query(CashMovement).filter(CashMovement.source_order_id == order['id']).count() == 1
    assert len(notifications) == 1
    db.close()
