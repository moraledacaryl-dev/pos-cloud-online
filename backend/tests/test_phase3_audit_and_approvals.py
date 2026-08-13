from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import AuditLog, ManagerApproval, Outlet, Register, User, CatalogItem, RoomChargePosting
from app.schemas.common import CashMovementCreate, InHouseBookingSnapshotCreate, OrderCreate, OrderPayPayload, OrderPaymentCreate, OrderVoidPayload, RegisterSessionOpen, RoomChargePostingStatusUpdate
from app.services.approval_guard import consume_protected_approval, protected_payload
from app.services.approval_service import authorize_approval_with_credentials, list_manager_approvals
from app.services.audit_service import list_audit_logs
from app.services.auth_service import hash_password
from app.services.pos_service import create_cash_movement, create_in_house_booking_snapshot, create_order, open_register_session, pay_order, update_room_charge_posting_status, void_order


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed(db):
    manager = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    cashier = User(username='cashier', full_name='Cashier', hashed_password=hash_password('secret123'), role='cashier', is_active=True)
    db.add_all([manager, cashier]); db.commit()
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet); db.commit(); db.refresh(outlet)
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    item = CatalogItem(menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add_all([register, item]); db.commit(); db.refresh(register); db.refresh(item); db.refresh(manager); db.refresh(cashier)
    return manager, cashier, register, item


def _authorize(db, requester, payload, *, approval_type, entity_type, entity_id, reason):
    grant = authorize_approval_with_credentials(
        db,
        requester=requester,
        manager_username='manager',
        manager_password='secret123',
        approval_type=approval_type,
        entity_type=entity_type,
        entity_id=entity_id,
        requested_reason=reason,
        protected_payload=protected_payload(payload),
    )
    payload.approval_grant_uuid = grant['approval_uuid']
    return grant


def test_phase3_creates_discount_void_and_cash_approval_rows():
    db = make_session()
    manager, cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0), user_id=manager.id)

    order_payload = OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 20}])
    _authorize(db, cashier, order_payload, approval_type='discount', entity_type='order', entity_id=None, reason='Discounted order creation')
    with consume_protected_approval(db, requester=cashier, payload=order_payload, approval_type='discount', entity_type='order', entity_id=None, requested_reason='Discounted order creation'):
        order = create_order(db, order_payload, user_id=cashier.id)

    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='cash', amount_applied=80, amount_received=100)]), user_id=cashier.id)

    void_payload = OrderVoidPayload(reason='Mistake')
    _authorize(db, cashier, void_payload, approval_type='void', entity_type='order', entity_id=order['id'], reason='Mistake')
    with consume_protected_approval(db, requester=cashier, payload=void_payload, approval_type='void', entity_type='order', entity_id=order['id'], requested_reason='Mistake') as grant:
        void_order(db, order['id'], 'Mistake', user_id=cashier.id, approved_by_user_id=grant['approved_by_user_id'])

    cash_payload = CashMovementCreate(register_session_id=session['id'], direction='out', movement_type='paid_out', category='Taxi', amount=50, note='Taxi')
    _authorize(db, cashier, cash_payload, approval_type='cash_paid_out', entity_type='cash_movement', entity_id=None, reason='Taxi')
    with consume_protected_approval(db, requester=cashier, payload=cash_payload, approval_type='cash_paid_out', entity_type='cash_movement', entity_id=None, requested_reason='Taxi') as grant:
        cash_payload.requires_approval = True
        create_cash_movement(db, cash_payload, approved_by_user_id=grant['approved_by_user_id'])

    approval_types = {row['approval_type'] for row in list_manager_approvals(db, limit=50)}
    actions = {row['action'] for row in list_audit_logs(db, limit=100)}
    assert 'discount' in approval_types
    assert 'void' in approval_types
    assert 'cash_paid_out' in approval_types
    assert 'order.created' in actions
    assert 'order.voided' in actions
    assert 'cash_movement.created' in actions


def test_room_charge_phase3_audit_and_dispute_approval():
    db = make_session()
    manager, cashier, register, item = seed(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=register.id, business_date='2026-04-20', shift_name='AM', opening_float=0), user_id=manager.id)
    snapshot = create_in_house_booking_snapshot(db, InHouseBookingSnapshotCreate(stay_date='2026-04-20', room_number='201', guest_name='Guest 201', guest_label='Rm 201 · Guest 201'))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest 201', lines=[{'catalog_item_id': item.id, 'quantity': 1, 'unit_price': 100, 'discount_amount': 0}]), user_id=cashier.id)
    pay_order(db, order['id'], OrderPayPayload(payments=[OrderPaymentCreate(tender_type='room_charge', amount_applied=100, room_charge_booking_snapshot_id=snapshot['id'])]), user_id=cashier.id)
    posting = db.query(RoomChargePosting).first()
    update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='posted_to_beds24', beds24_posting_reference='INV-201'), user_id=manager.id)
    update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='disputed', dispute_note='Guest questioned signature', approved_by_user_id=manager.id), user_id=manager.id, approved_by_user_id=manager.id)
    update_room_charge_posting_status(db, posting.id, RoomChargePostingStatusUpdate(posting_status='settled_at_frontdesk', later_payment_status='settled', payment_date='2026-04-21'), user_id=manager.id)
    actions = {row.action for row in db.query(AuditLog).all()}
    assert 'room_charge.created' in actions
    assert 'room_charge.booking_selected' in actions
    assert 'room_charge.marked_posted_manually' in actions
    assert 'room_charge.settlement_updated' in actions
    assert 'room_charge.dispute_resolved' in actions
    assert db.query(ManagerApproval).filter(ManagerApproval.approval_type == 'room_charge_dispute').count() == 1
