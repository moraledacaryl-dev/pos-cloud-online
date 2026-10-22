"""Reject forbidden order mutations from direct service callers."""

import uuid

import pytest
from sqlalchemy import create_engine, update
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.entities import AuditLog, Outlet, PosOrder, Register, RegisterSession, SyncOutboxEvent
from app.schemas.common import OrderUpdate
from app.services.pos_service import update_order, void_order


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def order_id_for(db, state):
    suffix = uuid.uuid4().hex[:10]
    outlet = Outlet(code=f"o-{suffix}", name="Test", is_active=True)
    db.add(outlet)
    db.flush()
    register = Register(outlet_id=outlet.id, code=f"r-{suffix}", name="Test", is_active=True)
    db.add(register)
    db.flush()
    shift = RegisterSession(session_code=f"s-{suffix}", register_id=register.id,
                            business_date="2026-09-07", status="closed")
    db.add(shift)
    db.flush()
    row = PosOrder(order_uuid=str(uuid.uuid4()), order_no=f"p-{suffix}",
                   register_session_id=shift.id, register_id=register.id,
                   business_date="2026-09-07", status=state, note="before",
                   total_amount=100, balance_due=100)
    db.add(row)
    db.commit()
    return row.id


@pytest.mark.parametrize("state", [
    "paid", "folio_pending", "refunded", "merged", "cancelled", "closed", "voided", "unknown",
])
def test_direct_edit_rejects_noneditable_state(db, state):
    order_id = order_id_for(db, state)
    with pytest.raises(ValueError, match="Unknown order state|Order action edit is not allowed"):
        update_order(db, order_id, OrderUpdate(note="after"))
    db.rollback()
    assert db.get(PosOrder, order_id).note == "before"
    assert db.query(AuditLog).count() == 0
    assert db.query(SyncOutboxEvent).count() == 0


@pytest.mark.parametrize("state", ["refunded", "merged", "cancelled", "closed", "unknown"])
def test_direct_void_rejects_terminal_state(db, state):
    order_id = order_id_for(db, state)
    with pytest.raises(ValueError, match="Unknown order state|Order action void is not allowed"):
        void_order(db, order_id, reason="test rejection")
    db.rollback()
    assert db.get(PosOrder, order_id).status == state
    assert db.query(AuditLog).count() == 0
    assert db.query(SyncOutboxEvent).count() == 0


def test_cached_draft_cannot_be_edited_after_database_state_changes(db):
    order_id = order_id_for(db, "draft")
    cached = db.get(PosOrder, order_id)
    assert cached.status == "draft"
    db.execute(
        update(PosOrder).where(PosOrder.id == order_id).values(status="paid"),
        execution_options={"synchronize_session": False},
    )
    assert cached.status == "draft"  # identity map is intentionally stale
    with pytest.raises(ValueError, match="Order action edit is not allowed"):
        update_order(db, order_id, OrderUpdate(note="after"))
    assert cached.status == "paid"
    db.rollback()


def test_cached_paid_cannot_be_voided_after_database_state_changes(db):
    order_id = order_id_for(db, "paid")
    cached = db.get(PosOrder, order_id)
    assert cached.status == "paid"
    db.execute(
        update(PosOrder).where(PosOrder.id == order_id).values(status="refunded"),
        execution_options={"synchronize_session": False},
    )
    assert cached.status == "paid"
    with pytest.raises(ValueError, match="Order action void is not allowed"):
        void_order(db, order_id, reason="test stale cache")
    assert cached.status == "refunded"
    db.rollback()
