"""Execute genuine POS outbox HTTP delivery against CI-only fake Accounting.

Two synthetic paid orders:
1) Accounting unavailable before recording => fails locally, then recovers.
2) Accounting records an order but returns 503 => a retry deduplicates by
   external_id with no second Accounting sale.
No live sale/payment is created. No production URLs or credentials are used.
"""
from __future__ import annotations

import asyncio
import json
import os
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from app.db.database import SessionLocal
from app.models.entities import Outlet, PosOrder, Register, RegisterSession, SyncOutboxEvent
from app.services.pos_service import save_setting_json
from app.services.sync_service import run_outbox_sync

BASE = "http://127.0.0.1:18991"
EXPECTED_DB = "pos_pass16_accounting_ci"


def guard() -> None:
    url = urlsplit(os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg:", "postgresql:", 1))
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("PASS16_ACCOUNTING_REPLAY_CI") == "1"
        and os.environ.get("ENVIRONMENT") == "staging"
        and url.scheme == "postgresql"
        and url.hostname == "127.0.0.1"
        and url.port == 5432
        and url.username == "pos"
        and url.path == "/" + EXPECTED_DB
        and not url.query
        and not url.fragment
    ):
        raise RuntimeError("Pass 16 replay can only use its isolated CI PostgreSQL fixture")


async def mode(value: str) -> None:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.post(BASE + "/__ci__/mode", json={"mode": value})
        r.raise_for_status()


async def state() -> dict:
    async with httpx.AsyncClient(timeout=5) as client:
        r = await client.get(BASE + "/__ci__/state")
        r.raise_for_status()
        return r.json()


def seed() -> tuple[int, int]:
    with SessionLocal() as db:
        if db.query(PosOrder).count() or db.query(SyncOutboxEvent).count():
            raise AssertionError("Replay CI database unexpectedly contains financial records")
        outlet = Outlet(code="PASS16-REPLAY", name="Isolated CI Counter", is_active=True)
        db.add(outlet)
        db.flush()
        register = Register(
            outlet_id=outlet.id, code="PASS16-REPLAY-REG", name="CI-only register",
            register_type="cash_drawer", cash_tender_label="Cash",
            default_order_type="dine_in", is_active=True,
        )
        db.add(register)
        db.flush()
        session = RegisterSession(
            session_code="PASS16-REPLAY-SESSION", register_id=register.id,
            business_date="2026-10-21", status="closed",
            opening_float=Decimal("0.00"), closing_expected_cash=Decimal("0.00"),
            variance_amount=Decimal("0.00"), blind_close=False,
        )
        db.add(session)
        db.flush()
        event_ids = []
        for index in (1, 2):
            ext = f"pass16-replay-order-{index}"
            order_no = f"PASS16-REPLAY-{index}"
            order = PosOrder(
                order_uuid=ext, order_no=order_no,
                register_session_id=session.id, register_id=register.id,
                business_date="2026-10-21", order_type="dine_in",
                status="paid", kitchen_status="queued",
                subtotal_amount=Decimal("42.00"), discount_amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"), service_charge_amount=Decimal("0.00"),
                total_amount=Decimal("42.00"), paid_amount=Decimal("42.00"),
                balance_due=Decimal("0.00"), primary_tender="cash",
                synced_to_accounting=False,
            )
            db.add(order)
            db.flush()
            payload = {
                "id": order.id,
                "order_uuid": ext,
                "order_no": order_no,
                "business_date": "2026-10-21",
                "order_type": "dine_in",
                "primary_tender": "cash",
                "lines": [{"catalog_item_id": index, "sku_code": "PASS16-CI-ITEM",
                           "item_name_snapshot": "Synthetic CI item",
                           "quantity": 1, "unit_price": "42.00", "discount_amount": "0.00"}],
            }
            row = SyncOutboxEvent(
                event_uuid=f"pass16-ci-outbox-{index}",
                aggregate_type="order", aggregate_id=order.id,
                event_type="order.finalized",
                idempotency_key=f"order.finalized:{order.id}",
                payload_json=json.dumps(payload, sort_keys=True), status="pending", retry_count=0,
            )
            db.add(row)
            db.flush()
            event_ids.append(row.id)
        save_setting_json(db, "accounting_sync", {
            "mode": "current_erp",
            "api_base": BASE + "/api",
            "api_token": "pass16-ci-token",
            "integration_secret": "",
            "sync_orders": True,
        }, username="pass16-ci")
        db.commit()
        return tuple(event_ids)


def read_event(event_id: int) -> tuple:
    with SessionLocal() as db:
        row = db.get(SyncOutboxEvent, event_id)
        order = db.get(PosOrder, row.aggregate_id)
        return (row.status, int(row.retry_count or 0), bool(order.synced_to_accounting),
                bool(row.last_error), row.synced_at is not None)


def retry_due(event_id: int) -> None:
    # Only the disposable test fixture has its backoff timer advanced for
    # deterministic recovery; production retry schedules remain untouched.
    with SessionLocal() as db:
        row = db.get(SyncOutboxEvent, event_id)
        assert row.status == "failed"
        row.next_retry_at = None
        db.commit()


async def main() -> None:
    guard()
    first_id, second_id = seed()
    initial = await state()
    assert initial["accepted"] == 0 and initial["attempts"] == []

    # Restrict each scenario to its own event using the queue limit.
    await mode("fail_before_accept")
    with SessionLocal() as db:
        outcome = await run_outbox_sync(db, limit=1)
    assert outcome["failed"] == 1 and outcome["synced"] == 0, outcome
    assert read_event(first_id)[:4] == ("failed", 1, False, True)
    assert (await state())["accepted"] == 0
    print("PASS16_ACCOUNTING_UNAVAILABLE_LOCAL_ORDER_PRESERVED=PASS")

    retry_due(first_id)
    await mode("healthy")
    with SessionLocal() as db:
        outcome = await run_outbox_sync(db, limit=1)
    assert outcome["synced"] == 1 and outcome["failed"] == 0, outcome
    assert read_event(first_id) == ("synced", 0, True, False, True), read_event(first_id)
    assert (await state())["accepted"] == 1
    print("PASS16_ACCOUNTING_OUTAGE_RECOVERY=PASS")

    # The first POS send is written downstream but its HTTP response says 503.
    # The second send must reuse the identity and receive deduplicated success.
    await mode("accept_then_503")
    with SessionLocal() as db:
        outcome = await run_outbox_sync(db, limit=5)
    assert outcome["failed"] == 1 and outcome["synced"] == 0, outcome
    assert read_event(second_id)[:4] == ("failed", 1, False, True)
    accepted_after_lost_ack = await state()
    assert accepted_after_lost_ack["accepted"] == 2
    print("PASS16_ACCOUNTING_LOST_ACK_RETAINED_FOR_RETRY=PASS")

    retry_due(second_id)
    await mode("healthy")
    with SessionLocal() as db:
        outcome = await run_outbox_sync(db, limit=5)
    assert outcome["synced"] == 1 and outcome["failed"] == 0, outcome
    assert read_event(second_id) == ("synced", 0, True, False, True), read_event(second_id)

    before_noop = await state()
    with SessionLocal() as db:
        noop = await run_outbox_sync(db, limit=5)
    after_noop = await state()
    assert noop["synced"] == 0 and noop["processed"] == 0, noop
    assert before_noop == after_noop, "Synced events were delivered a second time"
    assert after_noop["accepted"] == 2 and len(after_noop["identities"]) == 2
    assert len(after_noop["attempts"]) == 4, after_noop
    assert [entry["mode"] for entry in after_noop["attempts"]] == [
        "fail_before_accept", "healthy", "accept_then_503", "healthy",
    ]
    print("PASS16_ACCOUNTING_LOST_ACK_IDEMPOTENT_REPLAY=PASS")
    print("PASS16_ACCOUNTING_HTTP_REPLAY_CERTIFICATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
