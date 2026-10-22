"""Corrupt Accounting events are quarantined, never posted or silently synced.

Disposable SQLite database and fake HTTP transport only; no external writes.
"""

import asyncio

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.database import Base
from app.models.entities import SyncOutboxEvent
from app.services import sync_service


@pytest.fixture
def db_pair(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, future=True)

    class NoNetworkClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    async def no_refresh(_db, config):
        return config

    monkeypatch.setattr(sync_service, "get_sync_config", lambda _db: {
        "api_base": "https://accounting.invalid/api",
    })
    monkeypatch.setattr(sync_service, "_ensure_accounting_token", no_refresh)
    monkeypatch.setattr(sync_service.httpx, "AsyncClient", lambda **_kwargs: NoNetworkClient())
    with factory() as db:
        yield db, factory
    engine.dispose()


def add_order_event(db, *, index, payload_json, status="pending"):
    row = SyncOutboxEvent(
        event_uuid=f"invalid-accounting-payload-{index}",
        aggregate_type="order",
        aggregate_id=index,
        event_type="order.finalized",
        idempotency_key=f"invalid-accounting-payload-key-{index}",
        payload_json=payload_json,
        status=status,
    )
    db.add(row)
    db.commit()
    return row.id


@pytest.mark.parametrize("malformed", [
    "{unclosed",
    "[]",
    "null",
    '"an accidental string"',
    "42",
    "true",
])
def test_invalid_payload_blocks_persistently_and_does_not_starve_next_event(
    db_pair, monkeypatch, malformed,
):
    db, factory = db_pair
    corrupt_id = add_order_event(db, index=1, payload_json=malformed)
    healthy_id = add_order_event(db, index=2, payload_json='{"order_no":"POS-VALID-2"}')
    outgoing = []

    class Accepted:
        status_code = 201

    async def fake_push(_client, _base, _config, payload):
        outgoing.append(payload)
        return Accepted()

    monkeypatch.setattr(sync_service, "_push_order", fake_push)

    result = asyncio.run(sync_service.run_outbox_sync(db, limit=2))

    assert result["blocked"] == 1
    assert result["synced"] == 1
    assert result["processed"] == 2
    assert result["ok"] is False
    assert outgoing == [{"order_no": "POS-VALID-2"}]
    with factory() as verification:
        bad = verification.get(SyncOutboxEvent, corrupt_id)
        good = verification.get(SyncOutboxEvent, healthy_id)
        assert bad.status == "blocked"
        assert bad.synced_at is None
        assert "payload" in bad.last_error.lower()
        assert bad.last_attempt_at is not None
        assert good.status == "synced"


@pytest.mark.parametrize("malformed", ["{broken", "[]", "null"])
def test_manual_retry_does_not_send_invalid_payload(db_pair, monkeypatch, malformed):
    db, factory = db_pair
    event_id = add_order_event(db, index=1, payload_json=malformed, status="failed")
    outgoing = []

    async def forbidden_push(*args, **kwargs):
        outgoing.append((args, kwargs))
        raise AssertionError("Invalid events must not reach Accounting.")

    monkeypatch.setattr(sync_service, "_push_order", forbidden_push)
    result = asyncio.run(sync_service.retry_outbox_event(db, event_id))

    assert result["ok"] is False
    assert result["blocked"] is True
    assert outgoing == []
    with factory() as verification:
        row = verification.get(SyncOutboxEvent, event_id)
        assert row.status == "blocked"
        assert row.synced_at is None


def test_legacy_empty_object_payload_is_not_rejected_by_parser(db_pair):
    db, _factory = db_pair
    event_id = add_order_event(db, index=1, payload_json="{}")
    assert sync_service._load_payload(db.get(SyncOutboxEvent, event_id)) == {}
