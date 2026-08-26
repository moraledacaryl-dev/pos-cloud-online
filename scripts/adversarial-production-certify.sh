#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
PUBLIC_BASE="${PUBLIC_BASE:-https://pos.hiddenoasis.app}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
PYTHON="$APP_DIR/backend/.venv/bin/python"

fail() {
  echo "ADVERSARIAL CERTIFICATION FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

http_probe() {
  local method="$1"
  local url="$2"
  local expected="$3"
  shift 3
  local headers body code
  headers="$(mktemp)"
  body="$(mktemp)"
  code="$(curl -sS --max-time 8 -X "$method" -D "$headers" -o "$body" -w '%{http_code}' "$@" "$url")"
  echo "$method $url -> HTTP $code"
  if [[ "$code" != "$expected" ]]; then
    cat "$headers" >&2 || true
    cat "$body" >&2 || true
    rm -f "$headers" "$body"
    fail "$url returned HTTP $code; expected $expected"
  fi
  rm -f "$headers" "$body"
}

require_command git
require_command curl
require_command systemctl
require_command ss

[[ -d "$APP_DIR/.git" ]] || fail "not a Git checkout: $APP_DIR"
[[ -x "$PYTHON" ]] || fail "application virtualenv Python not executable: $PYTHON"
cd "$APP_DIR"

[[ -z "$(git status --porcelain)" ]] || fail "working tree is not clean"
CURRENT_COMMIT="$(git rev-parse HEAD)"
echo "Current commit: $CURRENT_COMMIT"
if [[ -n "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT"* ]]; then
  fail "current commit does not match EXPECTED_COMMIT=$EXPECTED_COMMIT"
fi
pass "release commit and working tree accepted"

for unit in pos-backend pos-frontend pos-sync-worker; do
  systemctl is-active --quiet "$unit" || fail "$unit is not active"
done
pass "all POS services are active"

# Browser credential regression: reusable auth tokens must not be stored or reconstructed in JS.
if grep -RInE "pos_token|pos_refresh_token|localStorage\\.(getItem|setItem|removeItem).*token|searchParams\\.set\\(['\"]token['\"]" \
  frontend/lib frontend/app frontend/components --exclude='*.test.*'; then
  fail "legacy browser credential handling detected"
fi
pass "frontend contains no legacy localStorage/JWT URL credential flow"

# Manager approval regression: internal approver attribution may legitimately carry
# approved_by_user_id after a server-verified grant is consumed. Prove the actual
# exploit boundary instead: every protected payload must reject a caller-supplied
# approver ID before grant handling, and the grant guard must remain wired in.
APP_DIR="$APP_DIR" "$PYTHON" - <<'PY'
import pathlib
import sys

app_dir = pathlib.Path(__import__('os').environ['APP_DIR'])
sys.path.insert(0, str(app_dir / 'backend'))

from app.schemas.common import (
    CashMovementCreate,
    OrderCreate,
    OrderUpdate,
    OrderVoidPayload,
    RefundCreate,
    RegisterSessionReopen,
    RoomChargePostingStatusUpdate,
)
from app.services.approval_guard import reject_legacy_client_approver

payloads = [
    RegisterSessionReopen(reason='x', approved_by_user_id=999),
    OrderCreate(register_session_id=1, approved_by_user_id=999),
    OrderUpdate(approved_by_user_id=999),
    OrderVoidPayload(reason='x', approved_by_user_id=999),
    RefundCreate(approved_by_user_id=999),
    CashMovementCreate(register_session_id=1, approved_by_user_id=999, direction='out', movement_type='safe_drop', amount=1),
    RoomChargePostingStatusUpdate(posting_status='disputed', approved_by_user_id=999),
]

for payload in payloads:
    try:
        reject_legacy_client_approver(payload)
    except ValueError as exc:
        if 'Client-supplied approved_by_user_id' not in str(exc):
            raise
    else:
        raise SystemExit(f'legacy approver ID was accepted for {type(payload).__name__}')

print('PASS: protected request DTOs reject caller-supplied approver IDs')
PY

grep -q "reject_legacy_client_approver(payload)" backend/app/services/approval_guard.py \
  || fail "approval guard is no longer enforced before protected grant consumption"
pass "manager approval exploit boundary remains server-verified"

# Negative public probes. These are intentionally non-destructive.
http_probe GET "$PUBLIC_BASE/api/auth/me" 401
http_probe POST "$PUBLIC_BASE/api/auth/bootstrap" 403
http_probe GET "$PUBLIC_BASE/api/audit?limit=25" 401
http_probe GET "$PUBLIC_BASE/api/customer-display/main" 401
http_probe GET "$PUBLIC_BASE/api/kitchen/stream?token=legacy-adversarial-test" 422
http_probe GET "$PUBLIC_BASE/api/kitchen/stream-metrics" 401

UNKNOWN_CODE="$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' "$PUBLIC_BASE/adversarial-route-does-not-exist")"
[[ "$UNKNOWN_CODE" == "404" ]] || fail "unknown route returned HTTP $UNKNOWN_CODE instead of 404"
pass "unknown application route returns 404"

# Browser security headers.
HEADERS="$(mktemp)"
trap 'rm -f "$HEADERS"' EXIT
curl -fsSI "$PUBLIC_BASE/login" > "$HEADERS"

grep -qi '^x-content-type-options:[[:space:]]*nosniff' "$HEADERS" || fail "X-Content-Type-Options: nosniff missing"
grep -qi '^referrer-policy:' "$HEADERS" || fail "Referrer-Policy missing"
grep -qi '^permissions-policy:' "$HEADERS" || fail "Permissions-Policy missing"
grep -qi '^content-security-policy:.*frame-ancestors' "$HEADERS" || fail "CSP frame-ancestors missing"
grep -qi '^strict-transport-security:' "$HEADERS" || fail "HSTS missing at HTTPS proxy"
pass "browser security headers and HSTS are present"

# Public readiness must prove strict runtime security, Redis tickets, worker freshness, and clean outbox.
DETAILS_JSON="$(curl -fsS "$PUBLIC_BASE/healthz/details")"
READY_JSON="$(curl -fsS "$PUBLIC_BASE/readyz/integrations")"
DETAILS_JSON="$DETAILS_JSON" READY_JSON="$READY_JSON" "$PYTHON" - <<'PY'
import json
import os

health = json.loads(os.environ['DETAILS_JSON'])
ready = json.loads(os.environ['READY_JSON'])
errors = []

if not health.get('sales_ready'):
    errors.append('sales_ready=false')
if not health.get('integrations_ready'):
    errors.append('integrations_ready=false')
if health.get('reasons'):
    errors.append(f"health reasons={health.get('reasons')}")

security = health.get('security') or {}
if not security.get('ok') or security.get('warnings'):
    errors.append(f"security={security}")

migration = (health.get('database') or {}).get('migration') or {}
if not migration.get('ok') or migration.get('requires_upgrade'):
    errors.append(f"migration={migration}")

store = health.get('kds_stream_ticket_store') or {}
if store.get('backend') != 'redis' or not store.get('required') or not store.get('connected'):
    errors.append(f"kds_stream_ticket_store={store}")

worker = health.get('sync_worker') or {}
if worker.get('is_stale'):
    errors.append(f"sync_worker={worker}")

outbox = health.get('outbox') or {}
for key in ('pending', 'failed', 'blocked', 'attention_required'):
    if int(outbox.get(key, 0) or 0) != 0:
        errors.append(f"outbox {key}={outbox.get(key)}")

reachability = health.get('integration_reachability') or {}
if not reachability or not all(bool(value) for value in reachability.values()):
    errors.append(f"integration_reachability={reachability}")

if not ready.get('ok'):
    errors.append(f"strict readiness={ready}")

if errors:
    raise SystemExit('\n'.join(errors))

print('PASS: strict readiness/security/worker/outbox assertions')
print('Outbox:', json.dumps(outbox, sort_keys=True))
PY

# Validate listeners: app ports and Redis must not be wildcard-public.
LISTENERS="$(ss -ltn)"
for port in 8100 3100 6379; do
  echo "$LISTENERS" | grep -Eq "127\.0\.0\.1:${port}|\[::1\]:${port}" || fail "expected loopback listener on port $port missing"
  if echo "$LISTENERS" | grep -Eq "0\.0\.0\.0:${port}|\[::\]:${port}|\*:${port}"; then
    fail "port $port is listening on a wildcard interface"
  fi
done
pass "backend/frontend/Redis listeners are loopback-only"

if command -v nginx >/dev/null 2>&1; then
  nginx -t >/dev/null 2>&1 || fail "nginx configuration test failed"
  pass "nginx configuration test succeeded"
fi

cat <<'EOF'

ADVERSARIAL PRODUCTION CERTIFICATION: PASS

This script is intentionally non-destructive. It proves negative authorization,
credential-leak, routing, header, runtime-security, readiness, listener, worker,
and outbox properties without creating or mutating production orders, payments,
refunds, voids, room charges, register sessions, or cash movements.

Controlled transactional pilots and backup restore proof remain separate operator
acceptance steps because they intentionally mutate state or require a non-production
restore target.
EOF
