#!/usr/bin/env bash
set -euo pipefail

BACKUP_FILE="${BACKUP_FILE:-}"
TARGET_DATABASE_URL="${TARGET_DATABASE_URL:-}"
NON_PRODUCTION_CONFIRM="${NON_PRODUCTION_CONFIRM:-}"
EXPECTED_HEAD="${EXPECTED_HEAD:-}"

fail() { echo "PASS 16 RESTORE REHEARSAL FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

[[ "$NON_PRODUCTION_CONFIRM" == "I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET" ]] || \
  fail "set NON_PRODUCTION_CONFIRM=I_CONFIRM_NON_PRODUCTION_RESTORE_TARGET"
[[ -n "$BACKUP_FILE" && -f "$BACKUP_FILE" ]] || fail "BACKUP_FILE must point to an existing PostgreSQL dump"
[[ -n "$TARGET_DATABASE_URL" ]] || fail "TARGET_DATABASE_URL is required"
[[ -n "$EXPECTED_HEAD" ]] || fail "EXPECTED_HEAD must explicitly match the migration revision in the backup"

case "${TARGET_DATABASE_URL,,}" in
  *hiddenoasis_pos_live*|*pos.hiddenoasis.app*|*production*)
    fail "refusing a restore target that appears to be production"
    ;;
esac

# A verbal confirmation and production-name blacklist alone cannot safely
# identify the target: a local PostgreSQL socket might point at a real database.
# Only an explicitly named disposable database on a loopback TCP address can
# be targeted. No production credentials or application database URLs are used.
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
if ! TARGET_DATABASE_NAME="$(TARGET_DATABASE_URL="$TARGET_DATABASE_URL" python3 - <<'PY'
import os
import re
from urllib.parse import urlsplit

try:
    url = urlsplit(os.environ["TARGET_DATABASE_URL"])
    name = url.path.removeprefix("/")
    safe = (
        url.scheme == "postgresql"
        and url.hostname in {"localhost", "127.0.0.1", "::1"}
        and bool(url.username)
        and not url.query
        and not url.fragment
        and re.fullmatch(r"pos_pass16_restore_[a-z0-9_]{2,40}", name)
    )
    if not safe:
        raise ValueError("requires a local disposable PostgreSQL database named pos_pass16_restore_*")
    print(name)
except (ValueError, TypeError) as exc:
    raise SystemExit(str(exc))
PY
)"; then
  fail "refusing a restore target that appears to be production or is not a local disposable database"
fi

command -v pg_restore >/dev/null 2>&1 || fail "pg_restore is required"
command -v psql >/dev/null 2>&1 || fail "psql is required"
pg_restore --list "$BACKUP_FILE" >/dev/null || fail "backup is not a readable PostgreSQL custom archive"

START_EPOCH="$(date +%s)"
echo "Restore rehearsal started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Target is explicitly NON-PRODUCTION."

# The target database must already be an empty disposable database. This script
# intentionally does not CREATE/DROP databases so a typo cannot destroy a host.
CONNECTED_DATABASE="$(psql -X -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -Atqc "select current_database();")"
[[ "$CONNECTED_DATABASE" == "$TARGET_DATABASE_NAME" ]] || fail "database connection did not resolve to the explicitly named disposable target"
TABLE_COUNT="$(psql -X -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -Atqc "select count(*) from pg_catalog.pg_tables where schemaname='public';")"
[[ "$TABLE_COUNT" == "0" ]] || fail "target public schema is not empty (table count=$TABLE_COUNT)"

pg_restore --exit-on-error --no-owner --no-privileges --dbname="$TARGET_DATABASE_URL" "$BACKUP_FILE"

REVISION="$(psql -X -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -Atqc "select version_num from alembic_version limit 1;")"
[[ "$REVISION" == "$EXPECTED_HEAD" ]] || fail "restored Alembic revision $REVISION does not match expected $EXPECTED_HEAD"

# Structural sanity only. Business reconciliation belongs in the evidence drill.
psql -X -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -Atqc "select 1 from users limit 1;" >/dev/null
psql -X -v ON_ERROR_STOP=1 "$TARGET_DATABASE_URL" -Atqc "select 1 from registers limit 1;" >/dev/null

END_EPOCH="$(date +%s)"
ELAPSED="$((END_EPOCH - START_EPOCH))"

pass "backup restored into a clean non-production database"
pass "restored migration revision is $REVISION"
echo "RESTORE_ELAPSED_SECONDS=$ELAPSED"
echo "PASS 16 NON-PRODUCTION RESTORE REHEARSAL: PASS"
