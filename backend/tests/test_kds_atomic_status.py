"""Kitchen status writes are single-transaction and notifications are post-commit.

Fixtures live only in disposable in-memory SQLite. No external integrations,
payments, Inventory writes, or production POS records are touched.
"""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import (
    CatalogItem,
    Outlet,
    PosOrder,
    PosOrderLine,
    Register,
    RegisterSession,
)
from app.schemas.common import KitchenLineStatusPayload
from app.services import pos_service


@pytest.fixture
def kitchen_db():
    engine = create_engine('sqlite:///:memory:', future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as db:
        outlet = Outlet(code='KDS-TEST', name='Kitchen', business_unit='F&B')
        db.add(outlet)
        db.flush()
        register = Register(outlet_id=outlet.id, code='KDS-REGISTER', name='Kitchen POS')
        db.add(register)
        db.flush()
        session = RegisterSession(
            session_code='KDS-SHIFT-TEST', register_id=register.id,
            business_date='2026-10-22', status='open',
        )
        item = CatalogItem(menu_item_name='Kitchen Test Item', display_name='Kitchen Test Item', price=100)
        db.add_all([session, item])
        db.flush()
        order = PosOrder(
            order_uuid='kds-order-uuid-test', order_no='KDS-ORDER-TEST',
            register_session_id=session.id, register_id=register.id,
            business_date='2026-10-22', status='sent', kitchen_status='queued',
        )
        db.add(order)
        db.flush()
        lines = [
            PosOrderLine(
                order_id=order.id, catalog_item_id=item.id, item_name_snapshot=f'Dish {number}',
                quantity=1, unit_price=100, line_total=100, prep_station='kitchen',
                kitchen_status='queued',
            )
            for number in (1, 2)
        ]
        db.add_all(lines)
        db.commit()
        yield db, order.id, [line.id for line in lines]
    engine.dispose()


def test_one_commit_saves_line_and_parent_then_notifies(kitchen_db, monkeypatch):
    db, order_id, line_ids = kitchen_db
    commits = []
    notifications = []
    event.listen(db, 'after_commit', lambda session: commits.append(True))

    def capture_publish(stations, *, reason, payload):
        order = db.get(PosOrder, order_id)
        line = db.get(PosOrderLine, payload['line_id'])
        # A notification must never precede a successful database commit.
        assert len(commits) == len(notifications) + 1
        assert order.kitchen_status == 'queued'
        assert line.kitchen_status == 'ready'
        notifications.append((stations, reason, payload))

    monkeypatch.setattr(pos_service, '_publish_kds_refresh', capture_publish)
    result = pos_service.update_kitchen_line_status(
        db, line_ids[0], KitchenLineStatusPayload(kitchen_status='ready')
    )

    assert len(commits) == 1
    assert len(notifications) == 1
    assert result['kitchen_status'] == 'ready'
    assert notifications[0][1] == 'ticket_line_updated'
    assert notifications[0][2]['order_id'] == order_id


def test_all_ready_parent_aggregates_in_same_commit(kitchen_db, monkeypatch):
    db, order_id, line_ids = kitchen_db
    monkeypatch.setattr(pos_service, '_publish_kds_refresh', lambda *args, **kwargs: None)
    pos_service.update_kitchen_line_status(
        db, line_ids[0], KitchenLineStatusPayload(kitchen_status='ready')
    )
    commits = []
    notifications = []
    event.listen(db, 'after_commit', lambda session: commits.append(True))

    def capture_publish(stations, *, reason, payload):
        assert len(commits) == 1
        assert db.get(PosOrder, order_id).kitchen_status == 'ready'
        assert db.get(PosOrderLine, line_ids[1]).kitchen_status == 'ready'
        notifications.append(reason)

    monkeypatch.setattr(pos_service, '_publish_kds_refresh', capture_publish)
    pos_service.update_kitchen_line_status(
        db, line_ids[1], KitchenLineStatusPayload(kitchen_status='ready')
    )
    assert len(commits) == 1
    assert notifications == ['ticket_line_updated']


def test_failed_commit_does_not_persist_half_a_kitchen_transition(kitchen_db, monkeypatch):
    db, order_id, line_ids = kitchen_db
    notifications = []
    monkeypatch.setattr(
        pos_service, '_publish_kds_refresh', lambda *args, **kwargs: notifications.append(True)
    )
    attempts = []
    def reject_commit():
        attempts.append(True)
        raise RuntimeError('synthetic database commit failure')

    monkeypatch.setattr(db, 'commit', reject_commit)
    with pytest.raises(RuntimeError, match='synthetic database commit failure'):
        pos_service.update_kitchen_line_status(
            db, line_ids[0], KitchenLineStatusPayload(kitchen_status='ready')
        )
    assert len(attempts) == 1
    assert notifications == []
    db.rollback()
    db.expire_all()
    assert db.get(PosOrderLine, line_ids[0]).kitchen_status == 'queued'
    assert db.get(PosOrder, order_id).kitchen_status == 'queued'


def test_invalid_kitchen_status_never_commits_or_notifies(kitchen_db, monkeypatch):
    db, order_id, line_ids = kitchen_db
    commits = []
    notifications = []
    event.listen(db, 'after_commit', lambda session: commits.append(True))
    monkeypatch.setattr(
        pos_service, '_publish_kds_refresh', lambda *args, **kwargs: notifications.append(True)
    )
    with pytest.raises(ValueError, match='Unsupported kitchen status'):
        pos_service.update_kitchen_line_status(db, line_ids[0], 'not-a-valid-status')
    assert commits == []
    assert notifications == []
    assert db.get(PosOrderLine, line_ids[0]).kitchen_status == 'queued'
    assert db.get(PosOrder, order_id).kitchen_status == 'queued'
