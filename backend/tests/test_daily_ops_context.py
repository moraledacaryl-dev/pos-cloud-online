from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.reports import build_daily_ops_context
from app.db.database import Base
from app.models.entities import CatalogItem, Outlet, PosOrder, PosOrderLine, PosOrderPayment, Register, RegisterSession, RoomChargePosting


def make_session():
    engine = create_engine('sqlite:///:memory:', future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    return TestingSession()


def test_daily_ops_context_aggregates_without_pii():
    db = make_session()
    outlet = Outlet(code='RESTO', name='Restaurant', business_unit='F&B')
    db.add(outlet)
    db.flush()
    register = Register(outlet_id=outlet.id, code='MAIN', name='Main')
    db.add(register)
    db.flush()
    session = RegisterSession(session_code='S-1', register_id=register.id, business_date='2026-06-08', status='open', opening_float=1000, variance_amount=-20)
    item = CatalogItem(menu_item_name='Burger', display_name='Burger', price=100)
    db.add_all([session, item])
    db.flush()
    order = PosOrder(
        order_uuid='ord-1',
        order_no='POS-1',
        register_session_id=session.id,
        register_id=register.id,
        business_date='2026-06-08',
        guest_name='Private Guest',
        status='paid',
        total_amount=150,
        paid_amount=150,
    )
    unpaid = PosOrder(
        order_uuid='ord-2',
        order_no='POS-2',
        register_session_id=session.id,
        register_id=register.id,
        business_date='2026-06-08',
        guest_name='Another Private Guest',
        status='open',
        total_amount=80,
        balance_due=80,
    )
    db.add_all([order, unpaid])
    db.flush()
    db.add(PosOrderLine(order_id=order.id, catalog_item_id=item.id, item_name_snapshot='Burger', quantity=1, unit_price=150, line_total=150))
    db.add(PosOrderPayment(order_id=order.id, tender_type='cash', amount_applied=100, amount_received=100, is_cash=True))
    db.add(PosOrderPayment(order_id=order.id, tender_type='gcash', amount_applied=50, amount_received=50))
    db.add(RoomChargePosting(posting_uuid='rc-1', order_id=order.id, booking_date='2026-06-08', service_date='2026-06-08', room_number='201', charge_amount=25, posting_status='pending_frontdesk_post'))
    db.commit()

    context = build_daily_ops_context(db, '2026-06-08')
    assert context['totals']['sales'] == 230
    assert context['totals']['cash'] == 100
    assert context['totals']['gcash'] == 50
    assert context['totals']['room_charges'] == 25
    assert context['counts']['unpaid_orders'] == 1
    assert context['counts']['pending_room_charges'] == 1
    assert context['drawer_variance'] == -20
    assert 'Private Guest' not in str(context)
