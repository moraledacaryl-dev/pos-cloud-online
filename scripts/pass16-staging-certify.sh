#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
TARGET_ENVIRONMENT="${TARGET_ENVIRONMENT:-}"
PUBLIC_BASE="${PUBLIC_BASE:-}"
BACKEND_BASE="${BACKEND_BASE:-http://127.0.0.1:8100}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
PRODUCTION_BASE="https://pos.hiddenoasis.app"

fail() { echo "PASS 16 STAGING CERTIFICATION FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
http_code() { curl -sS -o /dev/null -w '%{http_code}' "$1"; }

[[ "$TARGET_ENVIRONMENT" == "staging" ]] || fail "TARGET_ENVIRONMENT must be exactly staging"
[[ -n "$PUBLIC_BASE" ]] || fail "PUBLIC_BASE is required"
[[ "$PUBLIC_BASE" != "$PRODUCTION_BASE" ]] || fail "refusing to run staging certification against production"
[[ "$PUBLIC_BASE" != "$PRODUCTION_BASE/" ]] || fail "refusing to run staging certification against production"
[[ -d "$APP_DIR/.git" ]] || fail "not a git checkout: $APP_DIR"

cd "$APP_DIR"
[[ -z "$(git status --porcelain)" ]] || fail "working tree is not clean"
CURRENT_COMMIT="$(git rev-parse HEAD)"
if [[ -n "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" ]]; then
  fail "current commit $CURRENT_COMMIT does not match EXPECTED_COMMIT=$EXPECTED_COMMIT"
fi
pass "staging checkout and commit accepted"

for url in \
  "$BACKEND_BASE/healthz" \
  "$BACKEND_BASE/readyz" \
  "$BACKEND_BASE/readyz/integrations" \
  "$PUBLIC_BASE/" \
  "$PUBLIC_BASE/healthz" \
  "$PUBLIC_BASE/readyz" \
  "$PUBLIC_BASE/readyz/integrations"
do
  code="$(http_code "$url")"
  echo "$url -> HTTP $code"
  [[ "$code" == "200" ]] || fail "$url returned HTTP $code"
done
pass "staging liveness/readiness endpoints are healthy"

PUBLIC_DETAILS_CODE="$(http_code "$PUBLIC_BASE/healthz/details")"
[[ "$PUBLIC_DETAILS_CODE" == "404" ]] || fail "public detailed health must remain hidden; got HTTP $PUBLIC_DETAILS_CODE"
pass "staging detailed health is not publicly exposed"

if [[ -x "$APP_DIR/backend/.venv/bin/alembic" ]]; then
  (
    cd "$APP_DIR/backend"
    CURRENT="$($APP_DIR/backend/.venv/bin/alembic current 2>/dev/null | sed -n '1p')"
    HEADS="$($APP_DIR/backend/.venv/bin/alembic heads 2>/dev/null | sed -n '1p')"
    echo "Alembic current: $CURRENT"
    echo "Alembic heads:   $HEADS"
    [[ -n "$CURRENT" && -n "$HEADS" ]] || fail "unable to read Alembic revisions"
    [[ "$CURRENT" == "$HEADS" ]] || fail "staging migration is not at head"
  )
  pass "staging Alembic revision is current"
fi

cat <<'EOF'

PASS 16 STAGING AUTOMATED CERTIFICATION: PASS

This is a non-destructive staging gate. It does not prove backup restoration,
rollback timing, downstream transactional idempotency, physical peripherals,
offline recovery, or role acceptance. Record those separately in the Pass 16
evidence record before claiming literal operational acceptance.
EOF
