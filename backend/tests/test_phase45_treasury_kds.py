from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import CatalogItem, CashMovement, Outlet, Register, SyncOutboxEvent, User
from app.schemas.common import CashMovementCreate, KitchenLineStatusPayload, OrderCreate, RegisterSessionClose, RegisterSessionOpen
from app.services.auth_service import hash_password
from app.services.pos_service import close_register_session, create_cash_movement, create_order, list_kitchen_lines, open_register_session, update_kitchen_line_status


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def seed_registers(db):
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B', is_active=True)
    db.add(outlet)
    db.commit()
    db.refresh(outlet)
    main = Register(outlet_id=outlet.id, code='MAIN', name='Main Drawer', accounting_financial_account_id=1, accounting_financial_account_code='CASH-RESTO', is_active=True)
    side = Register(outlet_id=outlet.id, code='BAR', name='Bar Drawer', accounting_financial_account_id=2, accounting_financial_account_code='CASH-BAR', is_active=True)
    item = CatalogItem(menu_item_name='Burger', display_name='Burger', category_name='Meals', module_slug='restaurant', prep_station='kitchen', price=100, is_active=True, is_available=True)
    db.add_all([main, side, item])
    db.commit()
    db.refresh(main); db.refresh(side); db.refresh(item)
    return main, side, item


def seed_manager(db):
    user = User(username='manager', full_name='Manager', hashed_password=hash_password('secret123'), role='manager', is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_transfer_semantics_store_destination_and_emit_transfer_event():
    db = make_session()
    main, side, _item = seed_registers(db)
    manager = seed_manager(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=main.id, business_date='2026-04-20', shift_name='AM', opening_float=1000))

    movement = create_cash_movement(
        db,
        CashMovementCreate(
            register_session_id=session['id'],
            direction='out',
            movement_type='drawer_transfer',
            category='Drawer Transfer',
            amount=250,
            destination_register_id=side.id,
            note='Move float',
            approved_by_user_id=manager.id,
        ),
        approved_by_user_id=manager.id,
    )

    row = db.get(CashMovement, movement['id'])
    assert row.destination_register_id == side.id
    assert row.to_accounting_financial_account_id == side.accounting_financial_account_id
    assert row.transfer_group_uuid is not None
    assert row.requires_approval is True
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == 'transfer.created').count() == 1


def test_session_close_keeps_denominations_variance_note_and_signoff():
    db = make_session()
    main, _side, _item = seed_registers(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=main.id, business_date='2026-04-20', shift_name='AM', opening_float=500))
    closed = close_register_session(
        db,
        session['id'],
        RegisterSessionClose(
            closing_actual_cash=480,
            closing_note='Count completed',
            close_mode='verified',
            blind_close=False,
            variance_note='Short by one voided coffee not yet posted',
            sign_off_name='Caryl Moraleda',
            sign_off_role='Manager',
            denomination_lines=[{'line_label': '500x0', 'amount': 0, 'sort_order': 1}, {'line_label': '20x24', 'amount': 480, 'sort_order': 2}],
        ),
    )
    assert closed['close_mode'] == 'verified'
    assert closed['blind_close'] is False
    assert closed['variance_note'] == 'Short by one voided coffee not yet posted'
    assert closed['sign_off_name'] == 'Caryl Moraleda'
    assert len(closed['denomination_lines']) == 2


def test_kds_ack_partial_ready_and_ready_metrics_are_exposed():
    db = make_session()
    main, _side, item = seed_registers(db)
    session = open_register_session(db, RegisterSessionOpen(register_id=main.id, business_date='2026-04-20', shift_name='AM', opening_float=0))
    order = create_order(db, OrderCreate(register_session_id=session['id'], guest_name='Guest', lines=[{'catalog_item_id': item.id, 'quantity': 3, 'unit_price': 100, 'discount_amount': 0}]))
    line_id = order['lines'][0]['id']

    acknowledged = update_kitchen_line_status(db, line_id, KitchenLineStatusPayload(kitchen_status='acknowledged'), user_id=7)
    partial = update_kitchen_line_status(db, line_id, KitchenLineStatusPayload(kitchen_status='in_progress', item_readiness='partial', ready_quantity=1), user_id=7)
    ready = update_kitchen_line_status(db, line_id, KitchenLineStatusPayload(kitchen_status='ready'), user_id=7)
    rows = list_kitchen_lines(db, station='kitchen', statuses=['acknowledged', 'in_progress', 'ready'])
    line = next(row for row in rows if row['line_id'] == line_id)

    assert acknowledged['acknowledgement_state'] == 'acknowledged'
    assert partial['item_readiness'] == 'partial'
    assert partial['ready_quantity'] == 1
    assert ready['kitchen_status'] == 'ready'
    assert line['acknowledgement_state'] == 'acknowledged'
    assert line['item_readiness'] == 'ready'
    assert line['ready_quantity'] == 3
    assert line['prep_minutes'] is not None
