#!/usr/bin/env bash
set -euo pipefail

DB_NAME="${POS_BACKUP_DATABASE:-hiddenoasis_pos_live}"
BACKUP_DIR="${POS_BACKUP_DIR:-/var/backups/hiddenoasis/pos}"
RETENTION_DAYS="${POS_BACKUP_RETENTION_DAYS:-14}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FINAL_FILE="$BACKUP_DIR/pos-$TIMESTAMP.dump"
TMP_FILE="$FINAL_FILE.tmp"

umask 077

case "$DB_NAME" in
  hiddenoasis_pos_live) ;;
  *)
    echo "Refusing unexpected production backup database: $DB_NAME" >&2
    exit 2
    ;;
esac

if ! [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] || (( RETENTION_DAYS < 1 )); then
  echo "POS_BACKUP_RETENTION_DAYS must be a positive integer" >&2
  exit 2
fi

if [[ ! -d "$BACKUP_DIR" ]] || [[ ! -w "$BACKUP_DIR" ]]; then
  echo "Backup directory must already exist and be writable: $BACKUP_DIR" >&2
  exit 2
fi

cleanup() {
  rm -f -- "$TMP_FILE"
}
trap cleanup EXIT

pg_dump \
  --format=custom \
  --no-owner \
  --no-privileges \
  --file="$TMP_FILE" \
  "$DB_NAME"

pg_restore --list "$TMP_FILE" >/dev/null

test -s "$TMP_FILE"
mv -- "$TMP_FILE" "$FINAL_FILE"
chmod 0600 "$FINAL_FILE"

# Retention runs only after a new archive has been created and validated.
find "$BACKUP_DIR" \
  -maxdepth 1 \
  -type f \
  -name 'pos-*.dump' \
  -mtime "+$RETENTION_DAYS" \
  -delete

printf 'POS_BACKUP_FILE=%s\n' "$FINAL_FILE"
printf 'POS_BACKUP_BYTES=%s\n' "$(stat -c '%s' "$FINAL_FILE")"
printf 'POS_BACKUP_RETENTION_DAYS=%s\n' "$RETENTION_DAYS"
