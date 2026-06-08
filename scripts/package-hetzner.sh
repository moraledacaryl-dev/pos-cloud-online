#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/hiddenoasis-pos-online.tar.gz}"

export LC_ALL=C
export COPYFILE_DISABLE=1

tar \
  --no-xattrs \
  --exclude='.git' \
  --exclude='.DS_Store' \
  --exclude='__MACOSX' \
  --exclude='._*' \
  --exclude='*.zip' \
  --exclude='*.tar.gz' \
  --exclude='*.log' \
  --exclude='*.pid' \
  --exclude='.env' \
  --exclude='.env.production' \
  --exclude='*/.env.production' \
  --exclude='*/.env' \
  --exclude='*/.env.local' \
  --exclude='.venv' \
  --exclude='*/.venv' \
  --exclude='.pytest_cache' \
  --exclude='*/.pytest_cache' \
  --exclude='.coverage' \
  --exclude='*/.coverage' \
  --exclude='coverage' \
  --exclude='*/coverage' \
  --exclude='.mypy_cache' \
  --exclude='*/.mypy_cache' \
  --exclude='.ruff_cache' \
  --exclude='*/.ruff_cache' \
  --exclude='__pycache__' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='*.db' \
  --exclude='*.sqlite' \
  --exclude='*.sqlite3' \
  --exclude='backend/.env' \
  --exclude='backend/.venv' \
  --exclude='backend/uploads' \
  --exclude='frontend/.env.local' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/.next' \
  --exclude='.env.production' \
  --exclude='data' \
  --exclude='backups' \
  -czf "$OUT" \
  -C "$ROOT" .

echo "Created $OUT"
