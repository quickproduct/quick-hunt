#!/usr/bin/env bash
# Start the full AI Job Hunter stack (all services + workers)
# Usage: bash infra/scripts/quick_start.sh [--with-data]
#
#   --with-data   Start infra first, run migrations, then start app services

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

SCALE_FLAGS="
  --scale worker-scraping-bulk=${WORKER_SCRAPING_BULK_SCALE:-2}
  --scale worker-scraping-realtime=${WORKER_SCRAPING_REALTIME_SCALE:-8}
  --scale worker-enrichment=${WORKER_ENRICHMENT_SCALE:-3}
  --scale worker-maintenance=${WORKER_MAINTENANCE_SCALE:-1}
  --scale worker-cover-bulk=${WORKER_COVER_BULK_SCALE:-2}
  --scale worker-cover-ranking=${WORKER_COVER_RANKING_SCALE:-2}
  --scale worker-cover-generation=${WORKER_COVER_GENERATION_SCALE:-3}
  --scale worker-cover-workflow=${WORKER_COVER_WORKFLOW_SCALE:-2}
  --scale worker-email=${WORKER_EMAIL_SCALE:-2}
  --scale worker-agentic=${WORKER_AGENTIC_SCALE:-2}
"

if [[ "${1:-}" == "--with-data" ]]; then
    log "Starting infrastructure services (postgres, rabbitmq, redis)..."
    $COMPOSE up -d postgres rabbitmq redis
    log "Waiting for postgres to be healthy (10s)..."
    sleep 10
    log "Running database migrations..."
    $COMPOSE run --rm alembic
    log "Starting application services..."
    $COMPOSE up -d $SCALE_FLAGS
    log ""
    log "Stack is ready with migrations applied:"
else
    log "Starting all services..."
    $COMPOSE up -d $SCALE_FLAGS
    log ""
    log "Services started (run with --with-data to also apply migrations):"
fi

log "  API:        http://localhost:8001"
log "  API Docs:   http://localhost:8001/docs"
log "  Dashboard:  http://localhost:3001"
log "  RabbitMQ:   http://localhost:15672"
log "  Prometheus: http://localhost:9090"
log "  Grafana:    http://localhost:3002"
