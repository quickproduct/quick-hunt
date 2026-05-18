#!/usr/bin/env bash
# Restart one service or all services in the stack
# Usage: bash infra/scripts/quick_restart.sh [SERVICE_NAME]
#
# Examples:
#   bash infra/scripts/quick_restart.sh          # restart all
#   bash infra/scripts/quick_restart.sh api      # restart api only
#   bash infra/scripts/quick_restart.sh worker-email

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

SERVICE="${1:-}"

if [[ -n "$SERVICE" ]]; then
    log "Restarting service: $SERVICE"
    $COMPOSE restart "$SERVICE"
    log "Service '$SERVICE' restarted."
else
    log "Restarting all services..."
    $COMPOSE restart
    log "All services restarted."
fi
