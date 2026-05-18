#!/usr/bin/env bash
# PostgreSQL backup script
# Backs up the 'jobhunter' database from the Docker postgres container
# Stores timestamped dumps in infra/backups/; keeps last 7 days

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)/backups"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="$BACKUP_DIR/backup_${TIMESTAMP}.sql"
LATEST_LINK="$BACKUP_DIR/backup.sql"

DB_CONTAINER="${DB_CONTAINER:-postgres}"
DB_NAME="${DB_NAME:-jobhunter}"
DB_USER="${DB_USER:-jobhunter}"
DB_PASSWORD="${DB_PASSWORD:-jobhunter}"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup of database '$DB_NAME'..."

PGPASSWORD="$DB_PASSWORD" docker exec -e PGPASSWORD="$DB_PASSWORD" "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -d "$DB_NAME" --no-password > "$BACKUP_FILE"

ln -sf "$BACKUP_FILE" "$LATEST_LINK"

echo "[$(date)] Backup saved: $BACKUP_FILE"

find "$BACKUP_DIR" -name "backup_*.sql" -mtime +7 -delete && \
    echo "[$(date)] Old backups cleaned up (kept last 7 days)."

echo "[$(date)] Done."
