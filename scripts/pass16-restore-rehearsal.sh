#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:-}"
TARGET_DATABASE_URL="${TARGET_DATABASE_URL:-}"
NON_PRODUCTION_CONFIRM="${NON_PRODUCTION_CONFIRM:-}"
EXPECTED_HEAD="${EXPECTED_HEAD:-0009_customer_display_devices}"

fail() { echo "PASS 16 RESTORE REHEARSAL FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ "$NON_PRODUCTION_CONFIRM" == "I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET" ]] || \
  fail "set NON_PRODUCTION_CONFIRM=I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET"
[[ -n "$BACKUP_FILE" && -f "$BACKUP_FILE" ]] || fail "BACKUP_FILE must point to an existing PostgreSQL dump"
[[ -n "$TARGET_DATABASE_URL" ]] || fail "TARGET_DATABASE_URL is required"

case "${TARGET_DATABASE_URL,,}" in
  *hiddenoasis_pos_live*|*pos.hiddenoasis.app*|*production*)
    fail "refusing a restore target that appears to be production"
    ;;
esac

command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is required"
command -v psql >/dev/null 2>&1 || fail "psql is required"

START_EPOCH="$(date +%s)"
echo "Restore rehearsal started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Target is explicitly NON-PRODUCTION."

# The target database must already be an empty disposable database. This script
# intentionally does not CREATE/DROP databases so a typo cannot destroy a host.
TABLE_COUNT="$(psql "$TARGET_DATABASE_URL" -Atqc "select count(*) from pg_catalog.pg_tables where schemaname='public';")"
[[ "$TABLE_COUNT" == "0" ]] || fail "target public schema is not empty (table count=$TABLE_COUNT)"

pg_restore --exit-on-error --no-owner --no-privileges --dbname="$TARGET_DATABASE_URL" "$BACKUP_FILE"

REVISION="$(psql "$TARGET_DATABASE_URL" -Atqc "select version_num from alembic_version limit 1;")"
[[ "$REVISION" == "$EXPECTED_HEAD" ]] || fail "restored Alembic revision $REVISION does not match expected $EXPECTED_HEAD"

# Structural sanity only. Business reconciliation belongs in the evidence drill.
psql "$TARGET_DATABASE_URL" -Atqc "select 1 from users limit 1;" >/dev/null
psql "$TARGET_DATABASE_URL" -Atqc "select 1 from registers limit 1;" >/dev/null

END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"

pass "backup restored into a clean non-production database"
pass "restored migration revision is $REVISION"
echo "RESTORE_ELAPSED_SECONDS=$ELAPSED"
echo "PASS 16 NON-PRODUCTION RESTORE REHEARSAL: PASS"
