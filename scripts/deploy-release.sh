#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
TARGET_ENVIRONMENT="${TARGET_ENVIRONMENT:-}"
CONFIRM_DEPLOY="${CONFIRM_DEPLOY:-}"
EVIDENCE_DIR="${EVIDENCE_DIR:-/var/lib/hiddenoasis-pos/deploy-evidence}"
PUBLIC_BASE="${PUBLIC_BASE:-}"
ALLOW_ACCOUNTING_UNAVAILABLE="${ALLOW_ACCOUNTING_UNAVAILABLE:-false}"
CERTIFICATION_SCRIPT="${CERTIFICATION_SCRIPT:-scripts/production-certify.sh}"

fail() { echo "DEPLOY FAIL: $*" >&2; exit 1; }
wait_for_http() {
  local url="$1"
  local attempts="${2:-60}"
  local attempt
  for ((attempt = 1; attempt <= attempts; attempt += 1)); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  fail "$url did not become ready after $attempts attempts"
}

install_systemd_units() {
  install -o root -g root -m 0644 deploy/systemd/pos-backend.service /etc/systemd/system/pos-backend.service
  install -o root -g root -m 0644 deploy/systemd/pos-frontend.service /etc/systemd/system/pos-frontend.service
  install -o root -g root -m 0644 deploy/systemd/pos-sync-worker.service /etc/systemd/system/pos-sync-worker.service
  install -o root -g root -m 0644 deploy/systemd/pos-backup.service /etc/systemd/system/pos-backup.service
  install -o root -g root -m 0644 deploy/systemd/pos-backup.timer /etc/systemd/system/pos-backup.timer
  systemctl daemon-reload
}

run_production_backup() {
  systemctl reset-failed pos-backup.service >/dev/null 2>&1 || true
  systemctl start pos-backup.service
  [[ "$(systemctl show pos-backup.service --property=Result --value)" == 'success' ]] \
    || fail 'pos-backup.service did not complete successfully'
}

[[ "$CONFIRM_DEPLOY" == "YES" ]] || fail 'CONFIRM_DEPLOY must be exactly YES'
[[ "$EUID" -eq 0 ]] || fail 'deployment must run as root to manage canonical systemd units'
[[ "$TARGET_ENVIRONMENT" == "staging" || "$TARGET_ENVIRONMENT" == "production" ]] || fail 'TARGET_ENVIRONMENT must be staging or production'
[[ "$ALLOW_ACCOUNTING_UNAVAILABLE" == "true" || "$ALLOW_ACCOUNTING_UNAVAILABLE" == "false" ]] \
  || fail 'ALLOW_ACCOUNTING_UNAVAILABLE must be true or false'
if [[ -z "$PUBLIC_BASE" && "$TARGET_ENVIRONMENT" == "production" ]]; then
  PUBLIC_BASE='https://pos.hiddenoasis.app'
fi
[[ "$PUBLIC_BASE" =~ ^https://[^[:space:]]+$ ]] || fail 'PUBLIC_BASE must be the HTTPS URL for the selected environment'
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail 'EXPECTED_COMMIT must be a full 40-character lowercase commit SHA'
[[ -d "$APP_DIR/.git" ]] || fail "not a Git checkout: $APP_DIR"

cd "$APP_DIR"
[[ -f "$CERTIFICATION_SCRIPT" ]] || fail "certification script not found: $CERTIFICATION_SCRIPT"
[[ -z "$(git status --porcelain)" ]] || fail 'deployment checkout is not clean'
git fetch --prune origin
git cat-file -e "$EXPECTED_COMMIT^{commit}" || fail 'release commit is not available from the configured repository'

PREVIOUS_COMMIT="$(git rev-parse HEAD)"
STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$EVIDENCE_DIR"
EVIDENCE_FILE="$EVIDENCE_DIR/$EXPECTED_COMMIT.txt"

rollback_code() {
  local exit_code=$?
  if [[ $exit_code -eq 0 ]]; then return; fi
  echo "Deployment failed; restoring code commit $PREVIOUS_COMMIT" >&2
  git switch --detach "$PREVIOUS_COMMIT" || true
  install_systemd_units || true
  (cd backend && .venv/bin/python -m pip install -r requirements.lock) || true
  (cd frontend && npm ci && npm run build) || true
  install -d -o hiddenoasis -g hiddenoasis -m 0750 frontend/.next/cache || true
  systemctl restart pos-backend pos-sync-worker pos-frontend || true
  {
    echo "result=failed"
    echo "target_environment=$TARGET_ENVIRONMENT"
    echo "requested_commit=$EXPECTED_COMMIT"
    echo "restored_code_commit=$PREVIOUS_COMMIT"
    echo "started_at=$STARTED_AT"
    echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "note=Database migrations are forward-only during automated rollback; restore rehearsal policy governs schema rollback."
  } > "$EVIDENCE_FILE"
  exit "$exit_code"
}
trap rollback_code ERR

EXPECTED_COMMIT="$PREVIOUS_COMMIT" PUBLIC_BASE="$PUBLIC_BASE" \
  ALLOW_ACCOUNTING_UNAVAILABLE="$ALLOW_ACCOUNTING_UNAVAILABLE" CERTIFICATION_PHASE=predeploy bash "$CERTIFICATION_SCRIPT"
run_production_backup

git switch --detach "$EXPECTED_COMMIT"
ACTUAL_COMMIT="$(git rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$EXPECTED_COMMIT" ]] || fail "checked out $ACTUAL_COMMIT instead of $EXPECTED_COMMIT"

# Avoid serving a changing virtual environment or a partially replaced Next.js build.
systemctl stop pos-frontend pos-sync-worker pos-backend

(
  cd backend
  python3.12 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install -r requirements-dev.lock
  .venv/bin/ruff check app tests
  PYTHONPATH=. .venv/bin/pytest -q
)
(
  cd frontend
  npm ci
  npm run test:ui
  npm run build
)

install -d -o hiddenoasis -g hiddenoasis -m 0750 frontend/.next/cache
install_systemd_units
systemctl enable pos-backup.timer
systemctl restart pos-backend
systemctl restart pos-sync-worker
systemctl restart pos-frontend
wait_for_http 'http://127.0.0.1:8100/healthz'
wait_for_http 'http://127.0.0.1:3100/login'

EXPECTED_COMMIT="$EXPECTED_COMMIT" PUBLIC_BASE="$PUBLIC_BASE" \
  ALLOW_ACCOUNTING_UNAVAILABLE="$ALLOW_ACCOUNTING_UNAVAILABLE" CERTIFICATION_PHASE=postdeploy bash "$CERTIFICATION_SCRIPT"

{
  echo "result=passed"
  echo "target_environment=$TARGET_ENVIRONMENT"
  echo "deployed_commit=$EXPECTED_COMMIT"
  echo "previous_commit=$PREVIOUS_COMMIT"
  echo "started_at=$STARTED_AT"
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "units=pos-backend,pos-sync-worker,pos-frontend"
  echo "certification=passed"
  echo "accounting_unavailable_accepted=$ALLOW_ACCOUNTING_UNAVAILABLE"
  echo "backup=completed-before-deploy"
} > "$EVIDENCE_FILE"

trap - ERR
echo "DEPLOY PASS: $EXPECTED_COMMIT"
