#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
PUBLIC_BASE="${PUBLIC_BASE:-https://pos.hiddenoasis.app}"
BACKEND_BASE="${BACKEND_BASE:-http://127.0.0.1:8100}"
FRONTEND_BASE="${FRONTEND_BASE:-http://127.0.0.1:3100}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
ALLOW_ACCOUNTING_UNAVAILABLE="${ALLOW_ACCOUNTING_UNAVAILABLE:-false}"
CERTIFICATION_PHASE="${CERTIFICATION_PHASE:-postdeploy}"

fail() {
  echo "CERTIFICATION FAIL: $*" >&2
  exit 1
}

pass() {
  echo "PASS: $*"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

http_code() {
  curl -sS -o /dev/null -w '%{http_code}' "$1"
}

require_http_200() {
  local url="$1"
  local code
  code="$(http_code "$url")"
  [[ "$code" == "200" ]] || fail "$url returned HTTP $code"
  pass "$url returned HTTP 200"
}

require_http_200_or_known_accounting_degradation() {
  local url="$1"
  local code
  code="$(http_code "$url")"
  if [[ "$code" == "200" ]]; then
    pass "$url returned HTTP 200"
    return
  fi
  if [[ "$ALLOW_ACCOUNTING_UNAVAILABLE" == "true" && "$code" == "503" ]]; then
    pass "$url returned expected HTTP 503 while Accounting unavailability is explicitly accepted"
    return
  fi
  fail "$url returned HTTP $code"
}

require_command git
require_command curl
require_command python3
require_command systemctl

[[ "$ALLOW_ACCOUNTING_UNAVAILABLE" == "true" || "$ALLOW_ACCOUNTING_UNAVAILABLE" == "false" ]] \
  || fail "ALLOW_ACCOUNTING_UNAVAILABLE must be true or false"
[[ "$CERTIFICATION_PHASE" == "predeploy" || "$CERTIFICATION_PHASE" == "postdeploy" ]] \
  || fail "CERTIFICATION_PHASE must be predeploy or postdeploy"

[[ -d "$APP_DIR/.git" ]] || fail "not a git checkout: $APP_DIR"
cd "$APP_DIR"

if [[ -n "$(git status --porcelain)" ]]; then
  git status --short
  fail "working tree is not clean"
fi
pass "working tree is clean"

CURRENT_COMMIT="$(git rev-parse HEAD)"
echo "Current commit: $CURRENT_COMMIT"
if [[ -n "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT" && "$CURRENT_COMMIT" != "$EXPECTED_COMMIT"* ]]; then
  fail "current commit $CURRENT_COMMIT does not match EXPECTED_COMMIT=$EXPECTED_COMMIT"
fi
pass "git commit accepted"

for unit in pos-backend pos-frontend pos-sync-worker; do
  systemctl is-active --quiet "$unit" || fail "$unit is not active"
  pass "$unit is active"
done

require_http_200 "$BACKEND_BASE/healthz"
require_http_200 "$BACKEND_BASE/readyz"
require_http_200 "$BACKEND_BASE/internal/healthz/details"
require_http_200 "$FRONTEND_BASE/"
require_http_200 "$PUBLIC_BASE/"
require_http_200 "$PUBLIC_BASE/healthz"
require_http_200 "$PUBLIC_BASE/readyz"

if [[ "$CERTIFICATION_PHASE" == "postdeploy" ]]; then
  require_http_200_or_known_accounting_degradation "$BACKEND_BASE/readyz/integrations"
  require_http_200_or_known_accounting_degradation "$BACKEND_BASE/internal/readyz/integrations"
  require_http_200_or_known_accounting_degradation "$PUBLIC_BASE/readyz/integrations"
fi

PUBLIC_DETAILS_CODE="$(http_code "$PUBLIC_BASE/healthz/details")"
[[ "$PUBLIC_DETAILS_CODE" == "404" ]] || fail "$PUBLIC_BASE/healthz/details returned HTTP $PUBLIC_DETAILS_CODE instead of 404"
pass "public detailed health endpoint is not exposed"

DETAILS_JSON="$(curl -fsS "$BACKEND_BASE/internal/healthz/details")"
INTEGRATION_JSON="{}"
if [[ "$CERTIFICATION_PHASE" == "postdeploy" ]]; then
  INTEGRATION_JSON="$(curl -sS "$BACKEND_BASE/internal/readyz/integrations")"
fi

DETAILS_JSON="$DETAILS_JSON" INTEGRATION_JSON="$INTEGRATION_JSON" ALLOW_ACCOUNTING_UNAVAILABLE="$ALLOW_ACCOUNTING_UNAVAILABLE" CERTIFICATION_PHASE="$CERTIFICATION_PHASE" python3 - <<'PY'
import json
import os
import sys

health = json.loads(os.environ["DETAILS_JSON"])
ready = json.loads(os.environ["INTEGRATION_JSON"])
allow_accounting_unavailable = os.environ["ALLOW_ACCOUNTING_UNAVAILABLE"] == "true"
certification_phase = os.environ["CERTIFICATION_PHASE"]
reported_integration_reasons = set(ready.get("reasons") or [])
accounting_api = health.get("accounting_api", {})
accounting_is_unavailable = not bool(accounting_api.get("ok"))
allowed_integration_reasons = (
    {"accounting_unreachable", "outbox_failed_events", "outbox_blocked_events"}
    if allow_accounting_unavailable and accounting_is_unavailable
    else set()
)
disallowed_integration_reasons = reported_integration_reasons - allowed_integration_reasons

errors = []
if not health.get("sales_ready"):
    errors.append("sales_ready is false")
if certification_phase == "postdeploy" and not health.get("integrations_ready") and (
    not reported_integration_reasons or disallowed_integration_reasons
):
    errors.append(
        f"integrations_ready is false for disallowed reasons: {sorted(disallowed_integration_reasons or reported_integration_reasons)}"
    )
if not health.get("database", {}).get("migration", {}).get("ok"):
    errors.append("database migration state is not current")
if certification_phase == "postdeploy" and health.get("sync_worker", {}).get("is_stale"):
    errors.append("sync worker heartbeat is stale")
if certification_phase == "postdeploy" and not health.get("accounting_api", {}).get("reachable") and not allow_accounting_unavailable:
    errors.append("Accounting API is not reachable")

outbox = health.get("outbox", {})
for key in ("failed", "blocked", "attention_required") if certification_phase == "postdeploy" else ():
    if allow_accounting_unavailable and accounting_is_unavailable:
        # Every non-Inventory SyncOutboxEvent is delivered by run_outbox_sync to
        # Accounting. Inventory events are removed from these alerting counts
        # when that integration is disabled, so this backlog is the expected
        # consequence of the explicitly accepted Accounting outage.
        continue
    if int(outbox.get(key, 0) or 0) != 0:
        errors.append(f"outbox {key}={outbox.get(key)}")

reachability = health.get("integration_reachability", {})
degraded_reachability = {
    key: value
    for key, value in reachability.items()
    if value is False and not (allow_accounting_unavailable and key == "accounting_api")
}
if certification_phase == "postdeploy" and degraded_reachability:
    errors.append(f"integration reachability degraded: {degraded_reachability}")

if certification_phase == "postdeploy" and not ready.get("ok") and (
    not reported_integration_reasons or disallowed_integration_reasons
):
    errors.append(f"strict integration readiness failed: {ready.get('reasons', [])}")

if errors:
    print("CERTIFICATION FAIL:")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

if certification_phase == "predeploy":
    print("PASS: pre-deploy core baseline is ready; integration readiness is evaluated after the candidate starts")
elif allow_accounting_unavailable and accounting_is_unavailable and not disallowed_integration_reasons:
    print("PASS: production core is ready with explicitly accepted Accounting unavailability and Accounting outbox backlog")
else:
    print("PASS: production health payload is fully ready on local-only monitoring surface")
print(
    "Outbox:",
    json.dumps(
        {
            "total": outbox.get("total"),
            "pending": outbox.get("pending"),
            "failed": outbox.get("failed"),
            "blocked": outbox.get("blocked"),
            "attention_required": outbox.get("attention_required"),
            "oldest_unresolved_age_seconds": outbox.get("oldest_unresolved_age_seconds"),
        },
        sort_keys=True,
    ),
)
PY

if [[ -x "$APP_DIR/backend/.venv/bin/alembic" ]]; then
  (
    cd "$APP_DIR/backend"
    if [[ -f /etc/hiddenoasis/pos-backend.env ]]; then
      set -a
      # shellcheck disable=SC1091
      . /etc/hiddenoasis/pos-backend.env
      set +a
    fi
    CURRENT="$($APP_DIR/backend/.venv/bin/alembic current 2>/dev/null | sed -n '1p')"
    HEADS="$($APP_DIR/backend/.venv/bin/alembic heads 2>/dev/null | sed -n '1p')"
    echo "Alembic current: $CURRENT"
    echo "Alembic heads:   $HEADS"
    [[ -n "$CURRENT" && -n "$HEADS" ]] || fail "unable to read Alembic revisions"
  )
  pass "Alembic revision commands succeeded"
fi

if command -v nginx >/dev/null 2>&1; then
  nginx -t >/dev/null 2>&1 || fail "nginx configuration test failed"
  pass "nginx configuration test succeeded"
fi

cat <<'EOF'

AUTOMATED PRODUCTION CERTIFICATION: PASS

This script is intentionally non-destructive. It does not create orders, payments,
refunds, voids, room charges, cash movements, or register sessions.
A green automated certification proves the deployed code/runtime gate only.
Complete the dated evidence requirements in docs/PASS_16_OPERATIONAL_ACCEPTANCE.md
before declaring literal operational acceptance.
EOF
