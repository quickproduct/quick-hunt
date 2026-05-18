#!/usr/bin/env bash
# Stop the AI Job Hunter stack gracefully
# Usage: bash infra/scripts/quick_stop.sh [--clean]
#
#   --clean   Also remove volumes (DESTRUCTIVE — clears database data)

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

if [[ "${1:-}" == "--clean" ]]; then
    log "WARNING: Stopping stack and removing volumes (database data will be lost)..."
    $COMPOSE down -v
    log "Stack stopped and volumes removed."
else
    log "Stopping all services..."
    $COMPOSE down
    log "Stack stopped. Data volumes preserved."
fi
