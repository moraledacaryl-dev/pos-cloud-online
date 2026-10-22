"""Accounting worker must never consume Inventory or Operations outbox rows.

Uses an isolated SQLite database and an in-process fake HTTP client. No live
orders, production payment records, financial ledgers or integration APIs.
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

    async def no_auth_refresh(_db, config):
        return config

    monkeypatch.setattr(sync_service, "get_sync_config", lambda _db: {"api_base": "https://accounting.invalid/api"})
    monkeypatch.setattr(sync_service, "_ensure_accounting_token", no_auth_refresh)
    monkeypatch.setattr(sync_service.httpx, "AsyncClient", lambda **_kwargs: NoNetworkClient())
    with factory() as db:
        yield db, factory
    engine.dispose()


def add_event(db, index, kind, status):
    row = SyncOutboxEvent(
        event_uuid=f"group8-{index}",
        aggregate_type="order",
        aggregate_id=index,
        event_type=kind,
        idempotency_key=f"group8-key-{index}",
        payload_json="{}",
        status=status,
    )
    db.add(row)
    db.commit()
    return row.id


def persistent_status(factory, event_id):
    with factory() as check:
        return check.get(SyncOutboxEvent, event_id).status


def test_accounting_worker_leaves_foreign_pending_and_failed_rows_untouched(db_pair):
    db, factory = db_pair
    cases = [
        ("inventory.sale_completed", "pending"),
        ("inventory.sale_refunded", "failed"),
        ("operations.v2.order.finalized", "pending"),
        ("operations.v2.payment.refunded", "failed"),
    ]
    event_ids = [add_event(db, i, event_type, status)
                 for i, (event_type, status) in enumerate(cases, start=1)]

    result = asyncio.run(sync_service.run_outbox_sync(db, limit=100))

    assert result == {
        "ok": True, "processed": 0, "synced": 0,
        "failed": 0, "blocked": 0, "skipped": 0,
    }
    assert [persistent_status(factory, event_id) for event_id in event_ids] == [
        status for _event_type, status in cases
    ]


def test_foreign_events_cannot_starve_accounting_limit(db_pair, monkeypatch):
    db, factory = db_pair
    inventory_id = add_event(db, 1, "inventory.sale_completed", "pending")
    operations_id = add_event(db, 2, "operations.v2.order.finalized", "pending")
    accounting_id = add_event(db, 3, "order.finalized", "pending")
    posts = []

    class Response:
        status_code = 201

    async def fake_post(_client, base, config, payload):
        posts.append((base, config, payload))
        return Response()

    monkeypatch.setattr(sync_service, "_push_order", fake_post)

    result = asyncio.run(sync_service.run_outbox_sync(db, limit=1))

    assert result["processed"] == 1
    assert result["synced"] == 1
    assert posts == [("https://accounting.invalid/api", {"api_base": "https://accounting.invalid/api"}, {})]
    assert persistent_status(factory, accounting_id) == "synced"
    assert persistent_status(factory, inventory_id) == "pending"
    assert persistent_status(factory, operations_id) == "pending"


def test_unsupported_accounting_event_block_is_committed(db_pair):
    db, factory = db_pair
    event_id = add_event(db, 1, "unknown.accounting.event", "pending")

    result = asyncio.run(sync_service.run_outbox_sync(db, limit=1))

    assert result["blocked"] == 1
    assert result["ok"] is False
    assert persistent_status(factory, event_id) == "blocked"


def test_disabled_accounting_event_still_blocks_durably(db_pair, monkeypatch):
    db, factory = db_pair
    event_id = add_event(db, 1, "order.finalized", "pending")
    monkeypatch.setattr(sync_service, "get_sync_config", lambda _db: {
        "api_base": "https://accounting.invalid/api",
        "sync_orders": False,
    })

    result = asyncio.run(sync_service.run_outbox_sync(db, limit=1))

    assert result["blocked"] == 1
    assert persistent_status(factory, event_id) == "blocked"
