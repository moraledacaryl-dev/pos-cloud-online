"""Protect the financial settlement boundary from stale totals and direct calls."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import (
    CashMovement,
    CatalogItem,
    Outlet,
    PosOrder,
    PosOrderPayment,
    Register,
    SyncOutboxEvent,
)
from app.schemas.common import (
    OrderCreate,
    OrderPayPayload,
    OrderPaymentCreate,
    RegisterSessionOpen,
)
from app.services.pos_service import create_order, open_register_session, pay_order


def _draft_order():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autoflush=False, future=True)()
    outlet = Outlet(code="LOCKED", name="Locked Test", business_unit="F&B", is_active=True)
    db.add(outlet)
    db.flush()
    register = Register(
        outlet_id=outlet.id,
        code="LOCKED",
        name="Locked Drawer",
        accounting_financial_account_id=1,
        is_active=True,
    )
    catalog = CatalogItem(
        menu_item_name="Coffee",
        display_name="Coffee",
        category_name="Drinks",
        module_slug="cafe",
        prep_station="bar",
        price=100,
        is_active=True,
        is_available=True,
    )
    db.add_all([register, catalog])
    db.commit()
    session = open_register_session(
        db, RegisterSessionOpen(
            register_id=register.id,
            business_date="2026-04-19",
            shift_name="AM",
            opening_float=0,
        ),
    )
    order = create_order(
        db, OrderCreate(
            register_session_id=session["id"],
            lines=[{"catalog_item_id": catalog.id, "quantity": 1, "unit_price": 100}],
        ),
    )
    return db, order["id"]


def _assert_not_settled(db, order_id):
    assert db.get(PosOrder, order_id).status == "draft"
    assert db.query(PosOrderPayment).filter(PosOrderPayment.order_id == order_id).count() == 0
    assert db.query(CashMovement).filter(CashMovement.source_order_id == order_id).count() == 0
    assert db.query(SyncOutboxEvent).filter(SyncOutboxEvent.event_type == "order.finalized").count() == 0


@pytest.mark.parametrize("applied", ["99.99", "100.01", "-1", "NaN", "Infinity"])
def test_service_rejects_invalid_tender_without_financial_side_effects(applied):
    db, order_id = _draft_order()
    try:
        with pytest.raises(ValueError, match="Payment"):
            pay_order(
                db, order_id,
                OrderPayPayload(payments=[
                    OrderPaymentCreate(tender_type="cash", amount_applied=Decimal(applied)),
                ]),
            )
        db.rollback()
        _assert_not_settled(db, order_id)
    finally:
        db.close()


def test_service_rejects_split_overpayment_without_cash_or_accounting_events():
    db, order_id = _draft_order()
    try:
        with pytest.raises(ValueError, match="exactly equal"):
            pay_order(db, order_id, OrderPayPayload(payments=[
                OrderPaymentCreate(tender_type="cash", amount_applied=60),
                OrderPaymentCreate(tender_type="gcash", amount_applied=50, reference_no="GC-OVER",
                                   accounting_financial_account_id=2),
            ]))
        db.rollback()
        _assert_not_settled(db, order_id)
    finally:
        db.close()


def test_checkout_reloads_cached_order_total_under_lock_before_settlement():
    db, order_id = _draft_order()
    try:
        cached = db.get(PosOrder, order_id)
        assert cached.total_amount == 100
        # Deliberately leave the ORM identity map stale, as a preflight request
        # can be after a concurrent edit. A locked read must refresh this object.
        db.execute(
            update(PosOrder).where(PosOrder.id == order_id)
            .values(total_amount=200)
            .execution_options(synchronize_session=False)
        )
        db.commit()
        assert cached.total_amount == 100
        with pytest.raises(ValueError, match="exactly equal"):
            pay_order(db, order_id, OrderPayPayload(payments=[
                OrderPaymentCreate(tender_type="cash", amount_applied=100),
            ]))
        db.rollback()
        _assert_not_settled(db, order_id)
        assert db.get(PosOrder, order_id).total_amount == 200
    finally:
        db.close()


def test_checkout_cannot_settle_cancelled_order_via_internal_service():
    db, order_id = _draft_order()
    try:
        row = db.get(PosOrder, order_id)
        row.status = "cancelled"
        db.commit()
        with pytest.raises(ValueError, match="cannot be paid"):
            pay_order(db, order_id, OrderPayPayload(payments=[
                OrderPaymentCreate(tender_type="cash", amount_applied=100),
            ]))
        db.rollback()
        assert db.get(PosOrder, order_id).status == "cancelled"
        assert db.query(PosOrderPayment).filter(PosOrderPayment.order_id == order_id).count() == 0
    finally:
        db.close()
