"""Pass 16 migration round-trip and rollback safety on disposable restored POS data.

Runs only in GitHub CI against pos_pass16_restore_ci on loopback PostgreSQL.
Uses the synthetic recovered paid sale; never touches live services or DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

import psycopg

BACKEND = Path(__file__).resolve().parents[1]
PREVIOUS = "0012_catalog_pricing_rules"
CURRENT = "0013_generic_selling_rules"
TABLES = (
    "users", "outlets", "registers", "register_sessions", "catalog_items",
    "pos_orders", "pos_order_lines", "pos_order_payments",
    "cash_movements", "sync_outbox_events", "audit_logs",
)


def guard() -> str:
    source = os.environ.get("DATABASE_URL", "")
    target = os.environ.get("TARGET_DATABASE_URL", "")
    for value, database in (
        (source, "pos_pass16_source"),
        (target, "pos_pass16_restore_ci"),
    ):
        url = urlsplit(value)
        if not (
            url.scheme in {"postgresql", "postgresql+psycopg"}
            and url.hostname == "127.0.0.1"
            and url.port == 5432
            and url.username == "pos"
            and url.path == "/" + database
            and not url.query and not url.fragment
        ):
            raise RuntimeError("Migration CI refuses non-disposable PostgreSQL target")
    if not (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("PASS16_MIGRATION_CI") == "1"
        and os.environ.get("ENVIRONMENT") == "test"
    ):
        raise RuntimeError("Migration rehearsal requires isolated GitHub CI")
    return target.replace("postgresql+psycopg://", "postgresql://", 1)


def db_state(url: str) -> tuple[str, set[str], dict[str, tuple[int, str]]]:
    with psycopg.connect(url) as conn:
        revision = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        columns = {
            item[0] for item in conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'catalog_items'"
            )
        }
        digests = {}
        for table in TABLES:
            # 0013-only nullable selling-rule fields cannot exist at 0012.
            # Hash all other columns and all financial records across each step.
            expr = ("to_jsonb(t) - 'pricing_tags_json' - 'conditional_prices_json'"
                    if table == "catalog_items" else "to_jsonb(t)")
            rows = [
                row[0] for row in conn.execute(
                    f"SELECT {expr} FROM {table} t ORDER BY id"
                )
            ]
            payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
            digests[table] = (len(rows), hashlib.sha256(payload.encode()).hexdigest())
        assert digests["pos_orders"][0] == 1
        assert digests["pos_order_payments"][0] == 2
        assert digests["sync_outbox_events"][0] == 3
        assert digests["cash_movements"][0] == 1
        order = conn.execute(
            "SELECT total_amount, paid_amount, balance_due FROM pos_orders "
            "WHERE order_no = 'PASS16-SALE-1'"
        ).fetchone()
        assert tuple(str(x) for x in order) == ("180.00", "180.00", "0.00"), order
        tenders = conn.execute(
            "SELECT reference_no, amount_applied FROM pos_order_payments "
            "ORDER BY reference_no"
        ).fetchall()
        assert [(r[0], str(r[1])) for r in tenders] == [
            ("PASS16-CASH", "123.45"), ("PASS16-GCASH", "56.55")
        ], tenders
    return revision, columns, digests


def verify(url: str, revision: str, baseline: dict[str, tuple[int, str]]) -> None:
    actual, columns, current = db_state(url)
    assert actual == revision, (actual, revision)
    for field in ("pricing_tags_json", "conditional_prices_json"):
        assert (field in columns) == (revision == CURRENT), (field, revision)
    assert current == baseline, "Migration changed synthetic financial/catalog source records"


def migrate(url: str, *args: str, expect_failure: bool = False) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": url.replace("postgresql://", "postgresql+psycopg://", 1),
    }
    result = subprocess.run(
        ["alembic", *args],
        cwd=BACKEND, env=env, text=True, capture_output=True, check=False,
        timeout=120,
    )
    if expect_failure:
        assert result.returncode != 0, "Destructive pricing migration rollback was accepted"
        assert "0013 downgrade blocked: populated conditional pricing/tags" in (
            result.stderr + result.stdout
        ), "Downgrade refused for unexpected reason"
    else:
        assert result.returncode == 0, (
            f"Alembic {' '.join(args)} failed\n{result.stderr[-1200:]}"
        )


def main() -> None:
    url = guard()
    started = time.monotonic()
    revision, columns, baseline = db_state(url)
    assert revision == CURRENT and "conditional_prices_json" in columns
    print("PASS16_MIGRATION_SOURCE_FINANCIAL_BASELINE=PASS", flush=True)

    # Previous -> current -> previous -> current, preserving every synthetic
    # sale, tender, cash movement, audit entry, outbox ID and original SKU.
    for _ in range(2):
        migrate(url, "downgrade", PREVIOUS)
        verify(url, PREVIOUS, baseline)
        migrate(url, "upgrade", CURRENT)
        verify(url, CURRENT, baseline)
    migrate(url, "check")
    print("PASS16_MIGRATION_FINANCIAL_ROUNDTRIP=PASS", flush=True)

    with psycopg.connect(url) as conn:
        updated = conn.execute(
            "UPDATE catalog_items SET pricing_tags_json = %s, "
            "conditional_prices_json = %s WHERE sku_code = 'PASS16-ITEM'",
            ('["pass16-ci-tag"]', '{"condition":"pass16-ci"}'),
        ).rowcount
        assert updated == 1
    migrate(url, "downgrade", PREVIOUS, expect_failure=True)
    assert db_state(url)[0] == CURRENT, "Refused rollback nevertheless changed migration head"
    with psycopg.connect(url) as conn:
        values = conn.execute(
            "SELECT pricing_tags_json, conditional_prices_json FROM catalog_items "
            "WHERE sku_code = 'PASS16-ITEM'"
        ).fetchone()
        assert values == ('["pass16-ci-tag"]', '{"condition":"pass16-ci"}')
        conn.execute(
            "UPDATE catalog_items SET pricing_tags_json = NULL, "
            "conditional_prices_json = NULL WHERE sku_code = 'PASS16-ITEM'"
        )
    verify(url, CURRENT, baseline)
    migrate(url, "check")
    print("PASS16_POPULATED_PRICING_DOWNGRADE_REFUSED=PASS", flush=True)
    print(f"MIGRATION_CYCLE_ELAPSED_SECONDS={int(time.monotonic() - started)}")
    print("PASS16_SYNTHETIC_MIGRATION_REHEARSAL=PASS")


if __name__ == "__main__":
    main()
