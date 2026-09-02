#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/pos-cloud-online}"
EXPECTED_COMMIT="${EXPECTED_COMMIT:-}"
TARGET_ENVIRONMENT="${TARGET_ENVIRONMENT:-}"
CONFIRM_DEPLOY="${CONFIRM_DEPLOY:-}"
EVIDENCE_DIR="${EVIDENCE_DIR:-/var/lib/hiddenoasis-pos/deploy-evidence}"
PUBLIC_BASE="${PUBLIC_BASE:-}"

fail() { echo "DEPLOY FAIL: $*" >&2; exit 1; }
install_systemd_units() {
  install -o root -g root -m 0644 deploy/systemd/pos-backend.service /etc/systemd/system/pos-backend.service
  install -o root -g root -m 0644 deploy/systemd/pos-frontend.service /etc/systemd/system/pos-frontend.service
  install -o root -g root -m 0644 deploy/systemd/pos-sync-worker.service /etc/systemd/system/pos-sync-worker.service
  systemctl daemon-reload
}

[[ "$CONFIRM_DEPLOY" == "YES" ]] || fail 'CONFIRM_DEPLOY must be exactly YES'
[[ "$EUID" -eq 0 ]] || fail 'deployment must run as root to manage canonical systemd units'
[[ "$TARGET_ENVIRONMENT" == "staging" || "$TARGET_ENVIRONMENT" == "production" ]] || fail 'TARGET_ENVIRONMENT must be staging or production'
if [[ -z "$PUBLIC_BASE" && "$TARGET_ENVIRONMENT" == "production" ]]; then
  PUBLIC_BASE='https://pos.hiddenoasis.app'
fi
[[ "$PUBLIC_BASE" =~ ^https://[^[:space:]]+$ ]] || fail 'PUBLIC_BASE must be the HTTPS URL for the selected environment'
[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]] || fail 'EXPECTED_COMMIT must be a full 40-character lowercase commit SHA'
[[ -d "$APP_DIR/.git" ]] || fail "not a Git checkout: $APP_DIR"

cd "$APP_DIR"
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

EXPECTED_COMMIT="$PREVIOUS_COMMIT" PUBLIC_BASE="$PUBLIC_BASE" bash scripts/production-certify.sh
bash scripts/production-backup.sh

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
systemctl restart pos-backend
systemctl restart pos-sync-worker
systemctl restart pos-frontend

EXPECTED_COMMIT="$EXPECTED_COMMIT" PUBLIC_BASE="$PUBLIC_BASE" bash scripts/production-certify.sh

{
  echo "result=passed"
  echo "target_environment=$TARGET_ENVIRONMENT"
  echo "deployed_commit=$EXPECTED_COMMIT"
  echo "previous_commit=$PREVIOUS_COMMIT"
  echo "started_at=$STARTED_AT"
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "units=pos-backend,pos-sync-worker,pos-frontend"
  echo "certification=passed"
  echo "backup=completed-before-deploy"
} > "$EVIDENCE_FILE"

trap - ERR
echo "DEPLOY PASS: $EXPECTED_COMMIT"
