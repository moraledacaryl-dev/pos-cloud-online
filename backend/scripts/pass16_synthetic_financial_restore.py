"""Synthetic-only POS financial recovery fixture for the Pass 16 CI workflow.

This is a database-content restore regression, NOT an application checkout test,
production backup rehearsal, or evidence of actual operational RTO/RPO.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from decimal import Decimal
from urllib.parse import urlsplit

import psycopg

SOURCE_NAME = "pos_pass16_source"
TARGET_NAME = "pos_pass16_restore_ci"
TABLES = (
    "users",
    "outlets",
    "registers",
    "register_sessions",
    "catalog_items",
    "pos_orders",
    "pos_order_lines",
    "pos_order_payments",
    "cash_movements",
    "sync_outbox_events",
    "audit_logs",
)
TOTAL = Decimal("180.00")
CASH = Decimal("123.45")
GCASH = Decimal("56.55")


def _safe_url(raw: str, required_database: str) -> str:
    url = urlsplit(raw)
    if (
        url.scheme not in {"postgresql", "postgresql+psycopg"}
        or url.hostname not in {"127.0.0.1", "localhost"}
        or url.port != 5432
        or url.username != "pos"
        or url.path != f"/{required_database}"
        or url.query
        or url.fragment
    ):
        raise RuntimeError("Pass 16 synthetic drill refuses non-CI database address")
    return raw.replace("postgresql+psycopg://", "postgresql://", 1)


def _fixture_guard() -> tuple[str, str]:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("PASS16_SYNTHETIC_RESTORE") != "1"
        or os.environ.get("ENVIRONMENT") != "test"
    ):
        raise RuntimeError("Synthetic financial fixture is restricted to the isolated GitHub CI drill")
    return (
        _safe_url(os.environ.get("DATABASE_URL", ""), SOURCE_NAME),
        _safe_url(os.environ.get("TARGET_DATABASE_URL", ""), TARGET_NAME),
    )


def _insert_id(conn: psycopg.Connection, sql: str, params: tuple = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def seed(source_url: str) -> None:
    """Populate one synthetic paid sale and all associated financial facts."""
    with psycopg.connect(source_url) as conn:
        if conn.execute("SELECT COUNT(*) FROM pos_orders").fetchone()[0]:
            raise RuntimeError("Synthetic source database is not empty")
        user_id = _insert_id(
            conn, """
            INSERT INTO users (username, full_name, hashed_password, role, is_active, session_version)
            VALUES ('ci-pass16-synthetic', 'CI Fake Person', 'not-a-usable-password-hash',
                    'cashier', true, 1) RETURNING id
            """,
        )
        outlet_id = _insert_id(
            conn, """
            INSERT INTO outlets (code, name, is_active)
            VALUES ('PASS16-CI', 'Synthetic Recovery Outlet', true) RETURNING id
            """,
        )
        register_id = _insert_id(
            conn, """
            INSERT INTO registers (outlet_id, code, name, register_type, is_active)
            VALUES (%s, 'PASS16-CI-REG', 'Synthetic Recovery Register', 'cash_drawer', true)
            RETURNING id
            """, (outlet_id,),
        )
        session_id = _insert_id(
            conn, """
            INSERT INTO register_sessions
              (session_code, register_id, business_date, status, opened_by_user_id,
               closed_by_user_id, opening_float, closing_expected_cash,
               closing_actual_cash, variance_amount)
            VALUES ('PASS16-SESSION', %s, '2026-10-21', 'closed', %s,
                    %s, 200.00, 323.45, 323.45, 0.00)
            RETURNING id
            """, (register_id, user_id, user_id),
        )
        item_id = _insert_id(
            conn, """
            INSERT INTO catalog_items
              (menu_item_name, display_name, sku_code, category_name, price, is_active, is_available)
            VALUES ('Synthetic Test Food', 'Synthetic Test Food', 'PASS16-ITEM', 'CI-only',
                    90.00, true, true) RETURNING id
            """,
        )
        order_id = _insert_id(
            conn, """
            INSERT INTO pos_orders
              (order_uuid, order_no, register_session_id, register_id, cashier_user_id,
               business_date, order_type, status, kitchen_status, subtotal_amount,
               discount_amount, tax_amount, service_charge_amount, total_amount,
               paid_amount, balance_due, primary_tender)
            VALUES ('pass16-order-uuid', 'PASS16-SALE-1', %s, %s, %s, '2026-10-21',
                    'dine_in', 'paid', 'queued', 180.00, 0.00, 0.00, 0.00,
                    180.00, 180.00, 0.00, 'mixed') RETURNING id
            """, (session_id, register_id, user_id),
        )
        _insert_id(
            conn, """
            INSERT INTO pos_order_lines
              (order_id, catalog_item_id, item_name_snapshot, quantity,
               unit_price, discount_amount, line_total)
            VALUES (%s, %s, 'Synthetic Test Food', 2, 90.00, 0.00, 180.00)
            RETURNING id
            """, (order_id, item_id),
        )
        _insert_id(
            conn, """
            INSERT INTO pos_order_payments
              (order_id, tender_type, amount_applied, amount_received, change_given,
               is_cash, reference_no)
            VALUES (%s, 'cash', 123.45, 150.00, 26.55, true, 'PASS16-CASH')
            RETURNING id
            """, (order_id,),
        )
        gcash_id = _insert_id(
            conn, """
            INSERT INTO pos_order_payments
              (order_id, tender_type, amount_applied, amount_received, change_given,
               is_cash, reference_no)
            VALUES (%s, 'gcash', 56.55, 56.55, 0.00, false, 'PASS16-GCASH')
            RETURNING id
            """, (order_id,),
        )
        cash_id = _insert_id(
            conn, """
            INSERT INTO cash_movements
              (cash_event_uuid, register_session_id, register_id, source_order_id,
               event_date, direction, movement_type, category, amount, reference_no)
            VALUES ('pass16-cash-uuid', %s, %s, %s, '2026-10-21', 'in',
                    'cash_sale', 'Cash Sale', 123.45, 'PASS16-CASH')
            RETURNING id
            """, (session_id, register_id, order_id),
        )
        for index, (kind, aggregate, aggregate_id) in enumerate((
            ("cash_movement.created", "cash_movement", cash_id),
            ("payment.collected", "order_payment", gcash_id),
            ("order.finalized", "order", order_id),
        ), start=1):
            conn.execute(
                """
                INSERT INTO sync_outbox_events
                  (event_uuid, aggregate_type, aggregate_id, event_type,
                   idempotency_key, payload_json, status, retry_count)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', 0)
                """,
                (f"pass16-outbox-uuid-{index}", aggregate, aggregate_id, kind,
                 f"{kind}:{aggregate_id}",
                 json.dumps({"source": "pass16-synthetic", "order_no": "PASS16-SALE-1",
                             "total": "180.00", "id": aggregate_id})),
            )
        conn.execute(
            """
            INSERT INTO audit_logs
              (actor_user_id, actor_username, action, entity_type, entity_id, details_json)
            VALUES (%s, 'ci-pass16-synthetic', 'order.finalized', 'order', %s, %s)
            """,
            (user_id, str(order_id),
             json.dumps({"order_no": "PASS16-SALE-1", "status": "paid"})),
        )
    print("PASS16_SYNTHETIC_FINANCIAL_SEED=PASS")


def _digest(conn: psycopg.Connection, table: str) -> tuple[int, str]:
    rows = [r[0] for r in conn.execute(f"SELECT to_jsonb(t) FROM {table} t ORDER BY id")]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    return len(rows), hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assert_financial_integrity(conn: psycopg.Connection) -> None:
    row = conn.execute(
        """
        SELECT o.status, o.total_amount, o.paid_amount, o.balance_due,
               COUNT(p.id), SUM(p.amount_applied),
               SUM(CASE WHEN p.is_cash THEN p.amount_applied ELSE 0 END)
        FROM pos_orders o
        JOIN pos_order_payments p ON p.order_id = o.id
        WHERE o.order_no = 'PASS16-SALE-1'
        GROUP BY o.id
        """
    ).fetchone()
    assert row == ("paid", TOTAL, TOTAL, Decimal("0.00"), 2, TOTAL, CASH), row
    payments = conn.execute(
        """
        SELECT tender_type, amount_applied, amount_received, change_given
        FROM pos_order_payments ORDER BY tender_type
        """
    ).fetchall()
    assert payments == [
        ("cash", CASH, Decimal("150.00"), Decimal("26.55")),
        ("gcash", GCASH, GCASH, Decimal("0.00")),
    ], payments
    cash_row = conn.execute(
        "SELECT movement_type, direction, amount FROM cash_movements"
    ).fetchall()
    assert cash_row == [("cash_sale", "in", CASH)], cash_row
    outbox = conn.execute(
        "SELECT event_type, idempotency_key FROM sync_outbox_events ORDER BY event_type"
    ).fetchall()
    assert len(outbox) == 3 and len({x[1] for x in outbox}) == 3, outbox
    assert {x[0] for x in outbox} == {
        "cash_movement.created", "payment.collected", "order.finalized",
    }, outbox
    assert conn.execute(
        "SELECT COUNT(*) FROM audit_logs WHERE action = 'order.finalized'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM pos_order_lines WHERE quantity = 2 AND line_total = 180.00"
    ).fetchone()[0] == 1


def verify(source_url: str, target_url: str) -> None:
    """Compare all financial fixture rows byte-equivalently after restoration."""
    with psycopg.connect(source_url) as src, psycopg.connect(target_url) as dst:
        _assert_financial_integrity(src)
        _assert_financial_integrity(dst)
        for table in TABLES:
            original = _digest(src, table)
            restored = _digest(dst, table)
            if original != restored or original[0] == 0:
                raise AssertionError(f"restore diverged for {table}: count/hash mismatch")
            print(f"RECONCILED_{table}={original[0]} SHA256={original[1][:16]}")
    print("PASS16_SYNTHETIC_FINANCIAL_RECONCILIATION=PASS")


def main() -> None:
    source_url, target_url = _fixture_guard()
    if sys.argv[1:] == ["seed"]:
        seed(source_url)
    elif sys.argv[1:] == ["verify"]:
        verify(source_url, target_url)
    else:
        raise SystemExit("Usage: pass16_synthetic_financial_restore.py seed|verify")


if __name__ == "__main__":
    main()
