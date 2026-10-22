"""Paginated POS list must not issue one room-charge/refund query per order.

Disposable SQLite fixtures validate list/detail payload parity and SQL query
behavior. No real orders, customer records or integration services are used.
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import PosOrder, PosOrderPayment, RoomChargePosting
from app.services.pos_service import get_order, list_orders


@pytest.fixture
def data():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True, expire_on_commit=False)
    with factory() as db:
        order_ids = []
        for index in range(1, 13):
            order = PosOrder(
                order_uuid=f'group12-order-{index}',
                order_no=f'GROUP12-{index:04d}',
                register_session_id=1,
                register_id=1,
                business_date='2026-10-22',
                status='folio_pending' if index % 2 == 0 else 'draft',
                total_amount=Decimal('125.00'),
                paid_amount=Decimal('125.00') if index % 2 == 0 else Decimal('0.00'),
                balance_due=Decimal('0.00') if index % 2 == 0 else Decimal('125.00'),
            )
            db.add(order)
            db.flush()
            order_ids.append(order.id)
            if index % 2 == 0:
                payment = PosOrderPayment(
                    order_id=order.id,
                    tender_type='room_charge',
                    amount_applied=Decimal('125.00'),
                    amount_received=Decimal('125.00'),
                    change_given=Decimal('0.00'),
                    is_cash=False,
                )
                db.add(payment)
                db.flush()
                db.add(RoomChargePosting(
                    posting_uuid=f'group12-post-{index}',
                    order_id=order.id,
                    order_payment_id=payment.id,
                    booking_date='2026-10-22',
                    service_date='2026-10-22',
                    room_number=str(100 + index),
                    guest_label=f'Synthetic guest {index}',
                    posting_status='pending_frontdesk_post',
                    charge_amount=Decimal('125.00'),
                ))
        db.commit()
        yield engine, db, order_ids
    engine.dispose()


def _room_posting_sql(engine, work):
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _executemany):
        if statement.lstrip().lower().startswith('select'):
            statements.append(statement.lower())
    event.listen(engine, 'before_cursor_execute', capture)
    try:
        output = work()
    finally:
        event.remove(engine, 'before_cursor_execute', capture)
    posting_reads = [
        statement for statement in statements
        if 'from room_charge_postings' in statement
    ]
    return output, posting_reads, statements


def test_list_orders_batches_room_charge_lookup_once(data):
    engine, db, _ = data
    orders, posting_reads, _ = _room_posting_sql(
        engine, lambda: list_orders(db, limit=12),
    )
    assert len(orders) == 12
    assert len(posting_reads) == 1
    assert orders[0]['order_no'] == 'GROUP12-0012'
    assert orders[-1]['order_no'] == 'GROUP12-0001'


def test_postings_remain_isolated_and_nested_payment_metadata_is_preserved(data):
    _engine, db, ids = data
    orders = {order['id']: order for order in list_orders(db, limit=12)}
    for index, order_id in enumerate(ids, start=1):
        record = orders[order_id]
        if index % 2:
            assert record['room_charge_postings'] == []
            assert record['payment_breakdown'] == []
            continue
        assert len(record['room_charge_postings']) == 1
        posting = record['room_charge_postings'][0]
        assert posting['room_number'] == str(100 + index)
        assert posting['order_id'] == order_id
        assert posting['posting_status'] == 'pending_frontdesk_post'
        assert len(record['payment_breakdown']) == 1
        payment = record['payment_breakdown'][0]
        assert payment['room_charge_posting']['id'] == posting['id']
        assert payment['room_charge_posting_status'] == 'pending_frontdesk_post'
        # Existing single-order detail serialization remains unchanged.
        detail = get_order(db, order_id)
        assert detail['room_charge_postings'] == record['room_charge_postings']
        assert detail['payment_breakdown'] == record['payment_breakdown']


def test_empty_filtered_list_does_not_query_room_postings(data):
    engine, db, _ = data
    orders, posting_reads, _ = _room_posting_sql(
        engine, lambda: list_orders(db, business_date='1999-01-01', limit=12),
    )
    assert orders == []
    assert posting_reads == []


def test_list_orders_limit_only_fetches_postings_for_selected_page(data):
    _engine, db, ids = data
    rows = list_orders(db, limit=3)
    assert [row['id'] for row in rows] == list(reversed(ids[-3:]))
    assert [row['room_charge_postings'][0]['room_number'] if row['room_charge_postings'] else None for row in rows] == ['112', None, '110']
