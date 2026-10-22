"""Sync worklist regression: effective status filtering precedes the page limit.

All fixtures are isolated, disposable SQLite data: no worker, network,
production database, external payment or Accounting/Inventory write.
"""

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import pos_service


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)
    with factory() as session:
        yield session
    engine.dispose()


def add_event(db, *, status, event_type="order.finalized", payload=None):
    next_id = db.query(SyncOutboxEvent).count() + 1
    event = SyncOutboxEvent(
        event_uuid=f"sync-worklist-{next_id}",
        aggregate_type="order",
        aggregate_id=next_id,
        event_type=event_type,
        idempotency_key=f"sync-worklist-idempotency-{next_id}",
        status=status,
        payload_json=payload if isinstance(payload, str) else json.dumps(
            payload if payload is not None else {"lines": [{"external_menu_item_id": 42}]}
        ),
    )
    db.add(event)
    db.commit()
    return event.id


def test_suppressed_filter_finds_old_match_after_more_than_one_page(db, monkeypatch):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", True)
    oldest = add_event(
        db, status="blocked",
        payload={"lines": [{"external_menu_item_id": None}]},
    )
    for _ in range(240):
        add_event(db, status="synced")

    rows = pos_service.list_outbox_events(db, status="suppressed", limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == oldest
    assert rows[0]["stored_status"] == "blocked"
    assert rows[0]["status"] == "suppressed"
    assert "POS-local" in rows[0]["suppressed_reason"]


def test_failed_filter_skips_recent_effectively_suppressed_failures(db, monkeypatch):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", True)
    oldest = add_event(db, status="failed")
    for _ in range(4):
        add_event(db, status="failed", payload={"lines": [{"external_menu_item_id": None}]})
    rows = pos_service.list_outbox_events(db, status="failed", limit=1)
    assert len(rows) == 1
    assert rows[0]["id"] == oldest
    assert rows[0]["status"] == "failed"
    assert rows[0]["suppressed_reason"] is None


def test_default_worklist_still_returns_newest_rows_without_filter(db):
    ids = [add_event(db, status="synced") for _ in range(5)]
    rows = pos_service.list_outbox_events(db, limit=2)
    assert [r["id"] for r in rows] == ids[-1:-3:-1]


@pytest.mark.parametrize("payload", [
    '{"lines":"invalid-string"}',
    '{"lines":17}',
    '{"lines":{"external_menu_item_id":null}}',
    '{"lines":[1]}',
    '{"lines":[null]}',
    '{"lines":[{"external_menu_item_id":null},false]}',
    "invalid-json",
])
def test_malformed_line_payload_is_visible_not_silently_suppressed(db, monkeypatch, payload):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", True)
    event_id = add_event(db, status="failed", payload=payload)
    rows = pos_service.list_outbox_events(db, status="failed", limit=1)
    assert [row["id"] for row in rows] == [event_id]
    assert rows[0]["status"] == "failed"
    assert rows[0]["suppressed_reason"] is None
    assert pos_service.outbox_suppression_reason("order.finalized", payload) is None


def test_valid_mixed_pos_local_line_still_suppresses(db, monkeypatch):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", True)
    event_id = add_event(
        db, status="failed",
        payload={"lines": [{"external_menu_item_id": 99}, {"external_menu_item_id": None}]},
    )
    rows = pos_service.list_outbox_events(db, status="suppressed", limit=1)
    assert [row["id"] for row in rows] == [event_id]
    assert rows[0]["stored_status"] == "failed"


def test_inventory_disabled_suppression_visible_even_when_older(db, monkeypatch):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", False)
    old = add_event(db, status="inventory_retry", event_type="inventory.sale", payload={})
    for _ in range(5):
        add_event(db, status="synced")
    rows = pos_service.list_outbox_events(db, status="suppressed", limit=1)
    assert [row["id"] for row in rows] == [old]
    assert rows[0]["status"] == "suppressed"
    assert rows[0]["stored_status"] == "inventory_retry"
    assert "not enabled" in rows[0]["suppressed_reason"]


def test_effective_status_read_only_does_not_modify_event_rows(db, monkeypatch):
    monkeypatch.setattr(pos_service.settings, "inventory_integration_enabled", True)
    add_event(db, status="failed", payload={"lines": [{"external_menu_item_id": None}]})
    add_event(db, status="synced")
    statuses_before = db.query(SyncOutboxEvent.id, SyncOutboxEvent.status).order_by(SyncOutboxEvent.id).all()
    pos_service.list_outbox_events(db, status="suppressed", limit=1)
    pos_service.list_outbox_events(db, status="failed", limit=2)
    statuses_after = db.query(SyncOutboxEvent.id, SyncOutboxEvent.status).order_by(SyncOutboxEvent.id).all()
    assert statuses_before == statuses_after
    assert not db.dirty and not db.new and not db.deleted
