#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
TARGET_ENVIRONMENT="${TARGET_ENVIRONMENT:-}"
PUBLIC_BASE="${PUBLIC_BASE:-}"
BACKEND_BASE="${BACKEND_BASE:-http://127.0.0.1:8100}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
PUBLIC_API_PREFIX="${PUBLIC_API_PREFIX:-}"

fail() { echo "PASS 16 STAGING CERTIFICATION FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }
http_code() { curl --connect-timeout 3 --max-time 12 -sS -o /dev/null -w '%{http_code}' "$1"; }

[[ "$TARGET_ENVIRONMENT" == "staging" ]] || fail "TARGET_ENVIRONMENT must be exactly staging"
[[ -n "$PUBLIC_BASE" ]] || fail "PUBLIC_BASE is required"
[[ "$EXPECTED_COMMIT" =~ ^[a-f0-9]{40}$ ]] || fail "EXPECTED_COMMIT must be an explicit full 40-character SHA"
[[ "$PUBLIC_API_PREFIX" == "" || "$PUBLIC_API_PREFIX" == "/api" ]] || fail "PUBLIC_API_PREFIX must be empty or /api"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"

# Validate parsed hostnames rather than comparing only literal URL strings.
# A production URL with a port, alternate case, query, or trailing dot is unsafe.
if ! PUBLIC_BASE="$PUBLIC_BASE" BACKEND_BASE="$BACKEND_BASE" python3 - <<'PY'
import os
from urllib.parse import urlsplit

for label in ('PUBLIC_BASE', 'BACKEND_BASE'):
    raw = os.environ[label]
    parsed = urlsplit(raw)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            parsed.path not in ('', '/')):
        raise SystemExit('noncanonical HTTP origin')
    if parsed.hostname.lower().rstrip('.') == 'pos.hiddenoasis.app':
        raise SystemExit('refusing to run staging certification against production')
PY
then
  fail "refusing to run staging certification against production or unsafe origin"
fi

[[ -d "$APP_DIR/.git" ]] || fail "not a git checkout: $APP_DIR"
cd "$APP_DIR"
[[ -z "$(git status --porcelain)" ]] || fail "working tree is not clean"
CURRENT_COMMIT="$(git rev-parse HEAD)"
[[ "$CURRENT_COMMIT" == "$EXPECTED_COMMIT" ]] || \
  fail "current commit $CURRENT_COMMIT does not match EXPECTED_COMMIT=$EXPECTED_COMMIT"
pass "staging checkout and commit accepted"

# Backend internal health is loopback-only; it must report the real environment
# and core security, not merely accept the requested shell label "staging".
DIRECT_DETAILS="$(curl --connect-timeout 3 --max-time 12 -fsS "$BACKEND_BASE/internal/healthz/details")" || \
  fail "direct backend detailed health is unavailable"
if ! DIRECT_DETAILS="$DIRECT_DETAILS" python3 - <<'PY'
import json, os
report = json.loads(os.environ['DIRECT_DETAILS'])
if report.get('environment') != 'staging':
    raise SystemExit('backend environment is not staging')
if not report.get('database', {}).get('ok'):
    raise SystemExit('staging database is unhealthy')
if report.get('security', {}).get('warnings'):
    raise SystemExit('staging security warnings exist')
PY
then
  fail "backend runtime or security is not staging-ready"
fi
pass "backend runtime is staging with valid database and security"

for url in \
  "$BACKEND_BASE/healthz" \
  "$BACKEND_BASE/readyz" \
  "$BACKEND_BASE/readyz/integrations" \
  "$PUBLIC_BASE/login" \
  "$PUBLIC_BASE$PUBLIC_API_PREFIX/healthz" \
  "$PUBLIC_BASE$PUBLIC_API_PREFIX/readyz" \
  "$PUBLIC_BASE$PUBLIC_API_PREFIX/readyz/integrations"
do
  code="$(http_code "$url")"
  echo "$url -> HTTP $code"
  [[ "$code" == "200" ]] || fail "$url returned HTTP $code"
done
pass "staging public and backend liveness/readiness endpoints are healthy"

for path in /healthz/details /internal/healthz/details /internal/readyz /internal/readyz/integrations; do
  code="$(http_code "$PUBLIC_BASE$path")"
  [[ "$code" == "404" ]] || fail "private operational health path $path exposed HTTP $code"
done
pass "public gateway hides private health diagnostics"

if [[ -x "$APP_DIR/backend/.venv/bin/alembic" ]]; then
  ALEMBIC="$APP_DIR/backend/.venv/bin/alembic"
else
  ALEMBIC="$(command -v alembic || true)"
fi
[[ -n "$ALEMBIC" ]] || fail "alembic is required; staging migration verification cannot be skipped"
(
  cd "$APP_DIR/backend"
  CURRENT="$("$ALEMBIC" current 2>/dev/null | sed -n '1p')"
  HEADS="$("$ALEMBIC" heads 2>/dev/null | sed -n '1p')"
  echo "Alembic current: $CURRENT"
  echo "Alembic heads:   $HEADS"
  [[ -n "$CURRENT" && -n "$HEADS" ]] || fail "unable to read Alembic revisions"
  [[ "$CURRENT" == "$HEADS" ]] || fail "staging migration is not at head"
  "$ALEMBIC" check >/dev/null 2>&1 || fail "staging Alembic schema drift"
)
pass "staging Alembic revision and schema match"

cat <<'EOF'

PASS 16 STAGING AUTOMATED CERTIFICATION: PASS

Non-destructive staging runtime gate only. This does not certify an independent,
long-lived staging clone, production backup recovery or RTO/RPO, transactional
downstream integrations, physical devices, offline recovery or role acceptance.
EOF
