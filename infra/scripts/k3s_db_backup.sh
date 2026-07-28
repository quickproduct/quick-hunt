#!/usr/bin/env bash
# Back up the full PostgreSQL state from the local k3s postgres-0 pod.
# Dumps roles, globals, schemas, and data for every database via pg_dumpall.
#
# Usage:
#   bash infra/scripts/k3s_db_backup.sh
#   NAMESPACE=job-hunter POD=postgres-0 RETENTION_DAYS=14 bash infra/scripts/k3s_db_backup.sh

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$INFRA_DIR/backups/k3s-postgres}"
NAMESPACE="${NAMESPACE:-job-hunter}"
POD="${POD:-postgres-0}"
CONTAINER="${CONTAINER:-postgres}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
TIMESTAMP="$(date +"%Y-%m-%d_%H-%M-%S")"
BACKUP_FILE="$BACKUP_DIR/postgres_full_${TIMESTAMP}.sql.gz"
LATEST_LINK="$BACKUP_DIR/postgres_full_latest.sql.gz"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

command -v kubectl >/dev/null 2>&1 || die "kubectl is not installed or not on PATH"
command -v gzip >/dev/null 2>&1 || die "gzip is not installed or not on PATH"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

log "Checking pod $NAMESPACE/$POD..."
kubectl get pod "$POD" --namespace "$NAMESPACE" >/dev/null

log "Starting full PostgreSQL backup from $NAMESPACE/$POD..."
backup_complete=false
for attempt in 1 2 3; do
  : > "$BACKUP_FILE"
  if kubectl exec --namespace "$NAMESPACE" "$POD" --container "$CONTAINER" -- bash -lc '
    set -euo pipefail
    : "${POSTGRES_USER:?POSTGRES_USER is not set in the pod}"
    : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is not set in the pod}"
    command -v gzip >/dev/null 2>&1
    export PGPASSWORD="$POSTGRES_PASSWORD"
    pg_dumpall --username="$POSTGRES_USER" --clean --if-exists | gzip -9
  ' > "$BACKUP_FILE"; then
    backup_complete=true
    break
  fi

  log "Backup stream attempt $attempt failed; retrying with a fresh output file..."
  sleep 2
done

if [[ "$backup_complete" != "true" ]]; then
  rm -f "$BACKUP_FILE"
  die "Backup failed after 3 compressed transfer attempts"
fi

if [[ ! -s "$BACKUP_FILE" ]]; then
  rm -f "$BACKUP_FILE"
  die "Backup failed: dump file was empty"
fi

log "Validating compressed PostgreSQL dump..."
if ! gzip -t "$BACKUP_FILE"; then
  rm -f "$BACKUP_FILE"
  die "Backup failed: gzip integrity check failed"
fi

backup_header="$(gzip -cd "$BACKUP_FILE" | sed -n '1,5p')"
if ! grep -Fqx -- "-- PostgreSQL database cluster dump" <<< "$backup_header"; then
  rm -f "$BACKUP_FILE"
  die "Backup failed: unexpected dump header"
fi
chmod 600 "$BACKUP_FILE"

ln -sfn "$BACKUP_FILE" "$LATEST_LINK"

log "Backup saved: $BACKUP_FILE"
log "Latest symlink: $LATEST_LINK"

if [[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]]; then
  find "$BACKUP_DIR" -type f -name "postgres_full_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete
  log "Old k3s PostgreSQL backups cleaned up (kept last $RETENTION_DAYS days)."
else
  log "Skipping cleanup because RETENTION_DAYS is not a number: $RETENTION_DAYS"
fi

log "Done."
