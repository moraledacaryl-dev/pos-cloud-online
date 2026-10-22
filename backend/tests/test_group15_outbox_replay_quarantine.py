"""Group 15: immutable Operations events and fail-closed downstream envelopes.

Disposable SQLite and fake HTTP transports only. No production calls.
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


def _event(db, index, event_type, status, payload):
    row = SyncOutboxEvent(
        event_uuid=f"group15-{index}",
        aggregate_type="order",
        aggregate_id=index,
        event_type=event_type,
        idempotency_key=f"group15:{index}",
        payload_json=json.dumps(payload),
        status=status,
    )
    db.add(row)
    db.commit()
    return row


def _http_spy(monkeypatch, integration):
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
            requests.append((url, kwargs["json"]))
            return Response()

    monkeypatch.setattr(integration.httpx, "AsyncClient", Client)
    return requests


@pytest.mark.parametrize("status", [
    "operations_pending", "operations_retry", "operations_blocked",
    "synced", "suppressed",
])
def test_duplicate_operations_enqueue_keeps_original_snapshot_and_decision(db, monkeypatch, status):
    monkeypatch.setattr(operations.settings, "operations_integration_enabled", True)
    first = operations.enqueue_operations_event(
        db, "order.finalized", "order-15",
        title="Original", payload={"order_total": 100},
        subject_type="order", subject_id=15,
    )
    first.status = status
    first.retry_count = 4
    first.last_error = "Original delivery decision"
    first.next_retry_at = "2099-01-01T00:00:00"
    db.commit()
    original_payload = first.payload_json
    other = operations.enqueue_operations_event(
        db, "order.finalized", "order-15",
        title="Conflicting replay", payload={"order_total": 999},
        subject_type="order", subject_id=15,
    )
    assert other.id == first.id
    db.refresh(first)
    assert first.payload_json == original_payload
    assert first.status == status
    assert first.retry_count == 4
    assert first.last_error == "Original delivery decision"
    assert first.next_retry_at == "2099-01-01T00:00:00"
    assert db.query(SyncOutboxEvent).count() == 1


def test_operations_event_id_cannot_be_reused_for_different_event_type(db, monkeypatch):
    monkeypatch.setattr(operations.settings, "operations_integration_enabled", True)
    first = operations.enqueue_operations_event(
        db, "order.finalized", "order-15", title="First",
    )
    with pytest.raises(ValueError, match="different event type"):
        operations.enqueue_operations_event(
            db, "order.voided", "order-15", title="Collision",
        )
    db.refresh(first)
    assert first.event_type == "operations.v2.order.finalized"
    assert db.query(SyncOutboxEvent).count() == 1


@pytest.mark.parametrize("corrupt", [
    [],
    None,
    "accidental scalar",
    {},
    {"event_id": "wrong-type", "event_type": "refund.review_needed"},
])
def test_operations_worker_quarantines_bad_envelope_without_starving_good_event(
    db, monkeypatch, corrupt,
):
    monkeypatch.setattr(operations.settings, "operations_integration_enabled", True)
    monkeypatch.setattr(operations.settings, "operations_api_base", "https://operations.invalid/api")
    monkeypatch.setattr(operations.settings, "operations_integration_key", "isolated-key")
    calls = _http_spy(monkeypatch, operations)
    bad = _event(db, 1, "operations.v2.order.finalized", "operations_pending", corrupt)
    good = _event(
        db, 2, "operations.v2.order.finalized", "operations_pending",
        {"event_id": "good-event-15", "event_type": "order.finalized"},
    )

    result = asyncio.run(operations.run_operations_outbox_sync(db, limit=2))
    db.refresh(bad)
    db.refresh(good)
    assert result["blocked"] == 1
    assert result["synced"] == 1
    assert bad.status == "operations_blocked"
    assert bad.synced_at is None
    assert "payload" in bad.last_error.lower()
    assert good.status == "synced"
    assert len(calls) == 1
    assert calls[0][1]["event_id"] == "good-event-15"


VALID_INVENTORY = {
    "external_event_id": "pos:inventory-15:sale_completed",
    "external_sale_id": "inventory-15",
    "event_type": "sale_completed",
    "lines": [{"external_product_id": "SKU-15", "quantity": 2}],
}


@pytest.mark.parametrize("corrupt", [
    [],
    None,
    "not an object",
    {},
    {**VALID_INVENTORY, "lines": "bad-list"},
    {**VALID_INVENTORY, "lines": [1]},
    {**VALID_INVENTORY, "lines": [{"external_product_id": "", "quantity": 2}]},
    {**VALID_INVENTORY, "lines": [{"external_product_id": "SKU", "quantity": -1}]},
    {**VALID_INVENTORY, "lines": [{"external_product_id": "SKU", "quantity": "NaN"}]},
    {**VALID_INVENTORY, "_unmapped_lines": "not-list"},
    {**VALID_INVENTORY, "event_type": "sale_voided"},
])
def test_inventory_worker_quarantines_bad_payload_and_continues(
    db, monkeypatch, corrupt,
):
    monkeypatch.setattr(inventory.settings, "inventory_integration_enabled", True)
    monkeypatch.setattr(inventory.settings, "inventory_api_base", "https://inventory.invalid/api")
    monkeypatch.setattr(inventory.settings, "inventory_integration_token", "isolated-token")
    monkeypatch.setattr(inventory.settings, "inventory_pos_events_path", "/integrations/pos/events")
    calls = _http_spy(monkeypatch, inventory)
    bad = _event(db, 1, "inventory.sale_completed", "inventory_pending", corrupt)
    good = _event(db, 2, "inventory.sale_completed", "inventory_pending", VALID_INVENTORY)

    result = asyncio.run(inventory.run_inventory_outbox_sync(db, limit=2))
    db.refresh(bad)
    db.refresh(good)
    assert result["blocked"] == 1
    assert result["synced"] == 1
    assert bad.status == "blocked"
    assert bad.synced_at is None
    assert bad.next_retry_at is None
    assert good.status == "synced"
    assert len(calls) == 1
    assert calls[0][1]["external_sale_id"] == "inventory-15"


@pytest.mark.parametrize("kind", ["inventory", "operations"])
def test_invalid_json_is_quarantined_without_stopping_downstream_batch(
    db, monkeypatch, kind,
):
    module = inventory if kind == "inventory" else operations
    monkeypatch.setattr(
        module.settings, f"{kind}_integration_enabled", True,
    )
    if kind == "inventory":
        monkeypatch.setattr(inventory.settings, "inventory_api_base", "https://inventory.invalid/api")
        monkeypatch.setattr(inventory.settings, "inventory_integration_token", "test-token")
        monkeypatch.setattr(inventory.settings, "inventory_pos_events_path", "/integrations/pos/events")
        event_type = "inventory.sale_completed"
        status = "inventory_pending"
        valid = VALID_INVENTORY
        runner = inventory.run_inventory_outbox_sync
    else:
        monkeypatch.setattr(operations.settings, "operations_api_base", "https://operations.invalid/api")
        monkeypatch.setattr(operations.settings, "operations_integration_key", "test-key")
        event_type = "operations.v2.order.finalized"
        status = "operations_pending"
        valid = {"event_id": "good-15", "event_type": "order.finalized"}
        runner = operations.run_operations_outbox_sync
    calls = _http_spy(monkeypatch, module)
    bad = _event(db, 1, event_type, status, valid)
    good = _event(db, 2, event_type, status, valid)
    bad.payload_json = '{"malformed":'
    db.commit()

    result = asyncio.run(runner(db, limit=2))
    db.refresh(bad)
    db.refresh(good)
    assert result["blocked"] == 1
    assert result["synced"] == 1
    assert bad.status in {"blocked", "operations_blocked"}
    assert bad.synced_at is None
    assert good.status == "synced"
    assert len(calls) == 1
