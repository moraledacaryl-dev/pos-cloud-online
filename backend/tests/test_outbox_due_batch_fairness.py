"""Integration workers should select due rows before limiting their batches.

All events are synthetic and held in a disposable in-memory database; fake
HTTP transports ensure no external Accounting/Inventory/Operations writes.
"""

import asyncio
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import inventory_integration as inventory
from app.services import operations_integration as operations


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        yield session
    engine.dispose()


def put(db, index, *, kind, status, retry_at=None):
    payload = (
        {
            "external_event_id": f"synthetic-sale-{index}",
            "external_sale_id": f"synthetic-order-{index}",
            "event_type": "sale_completed",
            "lines": [{"external_product_id": "test-product", "quantity": 1}],
        }
        if kind.startswith("inventory.")
        else {"event_id": f"synthetic-ops-{index}", "event_type": "order.finalized"}
    )
    row = SyncOutboxEvent(
        event_uuid=f"group9-{index}",
        aggregate_type="order",
        aggregate_id=index,
        event_type=kind,
        idempotency_key=f"group9-key-{index}",
        status=status,
        next_retry_at=retry_at,
        retry_count=1 if retry_at else 0,
        payload_json=json.dumps(payload),
    )
    db.add(row)
    db.commit()
    return row.id


def fake_client(monkeypatch, module):
    requests = []

    class Response:
        status_code = 202
        text = ""

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, url, **kwargs):
            requests.append((url, kwargs))
            return Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    return requests


def test_inventory_deferred_retry_does_not_starve_ready_sale(db, monkeypatch):
    monkeypatch.setattr(inventory.settings, "inventory_integration_enabled", True)
    monkeypatch.setattr(inventory.settings, "inventory_api_base", "https://inventory.invalid/api")
    monkeypatch.setattr(inventory.settings, "inventory_integration_token", "test-token")
    monkeypatch.setattr(inventory.settings, "inventory_pos_events_path", "/integrations/pos/events")
    monkeypatch.setattr(inventory, "_now_text", lambda: "2026-10-22T08:00:00")
    requests = fake_client(monkeypatch, inventory)

    delayed_id = put(
        db, 1, kind="inventory.sale_completed",
        status="inventory_retry", retry_at="2099-01-01T00:00:00",
    )
    due_id = put(db, 2, kind="inventory.sale_completed", status="inventory_pending")

    result = asyncio.run(inventory.run_inventory_outbox_sync(db, limit=1))

    assert result["synced"] == result["processed"] == 1
    assert db.get(SyncOutboxEvent, due_id).status == "synced"
    delayed = db.get(SyncOutboxEvent, delayed_id)
    assert delayed.status == "inventory_retry"
    assert delayed.next_retry_at == "2099-01-01T00:00:00"
    assert delayed.last_attempt_at is None
    assert len(requests) == 1
    assert requests[0][1]["json"]["external_sale_id"] == "synthetic-order-2"


def test_operations_deferred_retry_does_not_starve_ready_event(db, monkeypatch):
    monkeypatch.setattr(operations.settings, "operations_integration_enabled", True)
    monkeypatch.setattr(operations.settings, "operations_api_base", "https://operations.invalid/api")
    monkeypatch.setattr(operations.settings, "operations_integration_key", "test-key")
    requests = fake_client(monkeypatch, operations)

    delayed_id = put(
        db, 1, kind="operations.v2.order.finalized",
        status="operations_retry", retry_at="2099-01-01T00:00:00",
    )
    due_id = put(db, 2, kind="operations.v2.order.finalized", status="operations_pending")

    result = asyncio.run(operations.run_operations_outbox_sync(db, limit=1))

    assert result["synced"] == result["processed"] == 1
    assert db.get(SyncOutboxEvent, due_id).status == "synced"
    delayed = db.get(SyncOutboxEvent, delayed_id)
    assert delayed.status == "operations_retry"
    assert delayed.next_retry_at == "2099-01-01T00:00:00"
    assert delayed.last_attempt_at is None
    assert len(requests) == 1
    assert requests[0][1]["json"]["event_id"] == "synthetic-ops-2"


def test_disabled_inventory_still_suppresses_deferred_event(db, monkeypatch):
    monkeypatch.setattr(inventory.settings, "inventory_integration_enabled", False)
    delayed_id = put(
        db, 1, kind="inventory.sale_completed",
        status="inventory_retry", retry_at="2099-01-01T00:00:00",
    )

    result = asyncio.run(inventory.run_inventory_outbox_sync(db, limit=1))

    assert result["skipped"] == 1
    assert db.get(SyncOutboxEvent, delayed_id).status == "suppressed"


def test_disabled_operations_still_suppresses_deferred_event(db, monkeypatch):
    monkeypatch.setattr(operations.settings, "operations_integration_enabled", False)
    delayed_id = put(
        db, 1, kind="operations.v2.order.finalized",
        status="operations_retry", retry_at="2099-01-01T00:00:00",
    )

    result = asyncio.run(operations.run_operations_outbox_sync(db, limit=1))

    assert result["skipped"] == 1
    assert db.get(SyncOutboxEvent, delayed_id).status == "suppressed"


def test_explicit_inventory_event_id_keeps_retry_backoff(db, monkeypatch):
    monkeypatch.setattr(inventory.settings, "inventory_integration_enabled", True)
    monkeypatch.setattr(inventory, "_now_text", lambda: "2026-10-22T08:00:00")
    requests = fake_client(monkeypatch, inventory)
    event_id = put(
        db, 1, kind="inventory.sale_completed",
        status="inventory_retry", retry_at="2099-01-01T00:00:00",
    )

    result = asyncio.run(inventory.run_inventory_outbox_sync(db, limit=1, event_id=event_id))

    assert result["processed"] == result["synced"] == 0
    assert result["skipped"] == 1
    assert db.get(SyncOutboxEvent, event_id).status == "inventory_retry"
    assert requests == []
