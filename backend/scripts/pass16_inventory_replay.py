"""Actual Inventory outbox delivery through local HTTP in disposable Pass 16 CI.

Proves delayed sale delivery, accepted-but-unacknowledged replay deduplication,
and stock reversal ordering with immutable original sale SKU/quantity.
Not a checkout, payment, real Inventory API, or production acceptance test.
"""
from __future__ import annotations

import asyncio
import os
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from app.db.database import SessionLocal
from app.models.entities import Outlet, PosOrder, Register, RegisterSession, SyncOutboxEvent
from app.services.inventory_integration import enqueue_inventory_event, run_inventory_outbox_sync

BASE = "http://127.0.0.1:18992"
DB_NAME = "pos_pass16_inventory_ci"
SKU = "PASS16-COFFEE"


def guard():
    db = urlsplit(os.environ.get("DATABASE_URL", "").replace("postgresql+psycopg:", "postgresql:", 1))
    inventory = urlsplit(os.environ.get("INVENTORY_API_BASE", ""))
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("PASS16_INVENTORY_REPLAY_CI") == "1"
        and os.environ.get("ENVIRONMENT") == "staging"
        and os.environ.get("INVENTORY_INTEGRATION_ENABLED") == "true"
        and db.scheme == "postgresql" and db.hostname == "127.0.0.1"
        and db.port == 5432 and db.username == "pos"
        and db.path == "/" + DB_NAME and not db.query and not db.fragment
        and inventory.scheme == "http" and inventory.hostname == "127.0.0.1"
        and inventory.port == 18992 and inventory.path == "/api/v1"
        and not inventory.query and not inventory.fragment
        and os.environ.get("INVENTORY_INTEGRATION_TOKEN") == "Pass16InventoryReplayToken2026_ABCDEF012345"
    ):
        raise RuntimeError("Pass 16 Inventory replay only accepts the isolated CI target and token")


async def mode(value: str):
    async with httpx.AsyncClient(timeout=5) as client:
        result = await client.post(BASE + "/__ci__/mode", json={"mode": value})
        result.raise_for_status()


async def state():
    async with httpx.AsyncClient(timeout=5) as client:
        result = await client.get(BASE + "/__ci__/state")
        result.raise_for_status()
        return result.json()


def seed():
    with SessionLocal() as db:
        if db.query(PosOrder).count() or db.query(SyncOutboxEvent).count():
            raise AssertionError("Inventory replay database is not isolated")
        outlet = Outlet(code="PASS16-INV", name="Synthetic Inventory CI outlet", is_active=True)
        db.add(outlet)
        db.flush()
        register = Register(
            outlet_id=outlet.id, code="PASS16-INV-REG",
            name="Synthetic Inventory register", register_type="cash_drawer",
            cash_tender_label="Cash", default_order_type="dine_in", is_active=True,
        )
        db.add(register)
        db.flush()
        session = RegisterSession(
            session_code="PASS16-INV-SESSION", register_id=register.id,
            business_date="2026-10-21", status="closed",
            opening_float=Decimal("0.00"), closing_expected_cash=Decimal("0.00"),
            variance_amount=Decimal("0.00"), blind_close=False,
        )
        db.add(session)
        db.flush()
        sale_ids = []
        void_id = None
        for index, qty in ((1, 2), (2, 3)):
            uuid = f"pass16-inventory-order-{index}"
            order = PosOrder(
                order_uuid=uuid, order_no=f"PASS16-INVENTORY-{index}",
                register_session_id=session.id, register_id=register.id,
                business_date="2026-10-21", order_type="dine_in",
                status="paid" if index == 1 else "voided", kitchen_status="queued",
                subtotal_amount=Decimal("42.00"), discount_amount=Decimal("0.00"),
                tax_amount=Decimal("0.00"), service_charge_amount=Decimal("0.00"),
                total_amount=Decimal("42.00"), paid_amount=Decimal("42.00"),
                balance_due=Decimal("0.00"), primary_tender="cash",
                synced_to_accounting=False,
            )
            db.add(order)
            db.flush()
            original = {
                "id": order.id, "order_uuid": uuid, "order_no": order.order_no,
                "lines": [{"sku_code": SKU, "quantity": qty,
                           "item_name_snapshot": "Synthetic coffee"}],
            }
            sale = enqueue_inventory_event(db, original, "sale_completed", commit=False)
            sale_ids.append(sale.id)
            if index == 2:
                # An intervening catalog SKU/quantity edit must not change an
                # already-recorded sale's stock reversal.
                modified = {
                    **original,
                    "lines": [{"sku_code": "UNSAFE-CHANGED-SKU", "quantity": 999,
                               "item_name_snapshot": "Modified catalog"}],
                }
                void = enqueue_inventory_event(db, modified, "sale_voided", commit=False)
                void_id = void.id
                db.flush()
                assert sale.id < void.id
                assert '"external_product_id": "PASS16-COFFEE"' in void.payload_json
                assert "UNSAFE-CHANGED-SKU" not in void.payload_json
        db.commit()
        assert void_id is not None
        return sale_ids[0], sale_ids[1], void_id


def event(event_id: int):
    with SessionLocal() as db:
        row = db.get(SyncOutboxEvent, event_id)
        return row.status, int(row.retry_count or 0), bool(row.last_error), bool(row.synced_at)


def due_now(event_id: int):
    # Advance only the disposable fixture's retry clock; do not bypass real
    # production backoff or alter any deployed Inventory instance.
    with SessionLocal() as db:
        row = db.get(SyncOutboxEvent, event_id)
        assert row.status == "inventory_retry"
        row.next_retry_at = None
        db.commit()


async def sync(limit: int = 25):
    with SessionLocal() as db:
        return await run_inventory_outbox_sync(db, limit=limit)


async def main():
    guard()
    first, second, reversal = seed()
    assert (await state())["accepted"] == 0

    await mode("fail_before_accept")
    first_result = await sync(limit=1)
    assert first_result["retrying"] == 1 and first_result["synced"] == 0, first_result
    assert event(first)[:3] == ("inventory_retry", 1, True)
    assert (await state())["accepted"] == 0
    print("PASS16_INVENTORY_OUTAGE_SOURCE_EVENT_PRESERVED=PASS")

    due_now(first)
    await mode("healthy")
    recovered = await sync(limit=1)
    assert recovered["synced"] == 1 and recovered["retrying"] == 0, recovered
    assert event(first)[0] == "synced" and event(first)[3] is True
    assert (await state())["stock_deltas"] == {SKU: "-2.0"}
    print("PASS16_INVENTORY_OUTAGE_RECOVERY=PASS")

    await mode("accept_then_503")
    lost_ack = await sync(limit=2)
    assert lost_ack["retrying"] == 1 and lost_ack["skipped"] == 1, lost_ack
    assert event(second)[0] == "inventory_retry"
    assert event(reversal)[0] == "inventory_pending"
    accepted = await state()
    assert accepted["accepted"] == 2
    assert accepted["stock_deltas"] == {SKU: "-5.0"}
    print("PASS16_INVENTORY_REVERSAL_WAITS_FOR_SALE=PASS")
    print("PASS16_INVENTORY_LOST_ACK_EVENT_RETRYABLE=PASS")

    due_now(second)
    await mode("healthy")
    replayed = await sync(limit=3)
    assert replayed["synced"] == 2 and replayed["retrying"] == 0, replayed
    assert event(second)[0] == "synced" and event(reversal)[0] == "synced"
    recorded = await state()
    assert recorded["accepted"] == 3 and recorded["stock_deltas"] == {SKU: "-2.0"}
    assert len(recorded["attempts"]) == 5, recorded
    assert [x["mode"] for x in recorded["attempts"]] == [
        "fail_before_accept", "healthy", "accept_then_503", "healthy", "healthy",
    ]
    print("PASS16_INVENTORY_LOST_ACK_IDEMPOTENT_REPLAY=PASS")
    print("PASS16_INVENTORY_ORIGINAL_SKU_REVERSAL=PASS")

    noop = await sync(limit=25)
    latest = await state()
    assert noop["processed"] == 0 and noop["synced"] == 0, noop
    assert latest == recorded
    print("PASS16_INVENTORY_NO_REDELIVERY_AFTER_ACK=PASS")
    print("PASS16_INVENTORY_HTTP_REPLAY_CERTIFICATION=PASS")


if __name__ == "__main__":
    asyncio.run(main())
