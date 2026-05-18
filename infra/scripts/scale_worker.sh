#!/usr/bin/env bash
# Scale a specific Celery worker type to the given number of replicas
# Usage: bash infra/scripts/scale_worker.sh WORKER_NAME REPLICAS
#
# Examples:
#   bash infra/scripts/scale_worker.sh worker-cover-generation 5
#   bash infra/scripts/scale_worker.sh worker-scraping-bulk 0   # pause
#
# Valid worker names:
#   worker-scraping-bulk, worker-scraping-realtime, worker-enrichment,
#   worker-maintenance, worker-cover-bulk, worker-cover-ranking,
#   worker-cover-generation, worker-cover-workflow, worker-email, worker-agentic

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

WORKER="${1:?Usage: scale_worker.sh WORKER_NAME REPLICAS}"
REPLICAS="${2:?Usage: scale_worker.sh WORKER_NAME REPLICAS}"

VALID_WORKERS=(
    worker-scraping-bulk worker-scraping-realtime worker-enrichment
    worker-maintenance worker-cover-bulk worker-cover-ranking
    worker-cover-generation worker-cover-workflow worker-email worker-agentic
)

VALID=0
for w in "${VALID_WORKERS[@]}"; do
    [[ "$w" == "$WORKER" ]] && VALID=1 && break
done

if [[ $VALID -eq 0 ]]; then
    echo "ERROR: Unknown worker '$WORKER'"
    echo "Valid workers: ${VALID_WORKERS[*]}"
    exit 1
fi

if ! [[ "$REPLICAS" =~ ^[0-9]+$ ]]; then
    echo "ERROR: REPLICAS must be a non-negative integer, got: $REPLICAS"
    exit 1
fi

log "Scaling $WORKER to $REPLICAS replicas..."
$COMPOSE up -d --no-deps --scale "$WORKER=$REPLICAS" "$WORKER"
log "$WORKER scaled to $REPLICAS."
