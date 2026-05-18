#!/usr/bin/env bash
# Pull latest image(s) and redeploy a service (or all services)
# Usage: bash infra/scripts/deploy_update.sh [SERVICE_NAME]
#
# Examples:
#   bash infra/scripts/deploy_update.sh         # rebuild & redeploy all
#   bash infra/scripts/deploy_update.sh api     # rebuild & redeploy api only

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

SERVICE="${1:-}"

if [[ -n "$SERVICE" ]]; then
    log "Pulling latest images for: $SERVICE"
    $COMPOSE pull "$SERVICE" 2>/dev/null || true

    log "Building $SERVICE..."
    $COMPOSE build "$SERVICE"

    log "Redeploying $SERVICE..."
    $COMPOSE up -d --no-deps "$SERVICE"

    log "Service '$SERVICE' deployed successfully."
else
    log "Pulling latest base images..."
    $COMPOSE pull 2>/dev/null || true

    log "Building all services..."
    $COMPOSE build

    log "Redeploying all services..."
    $COMPOSE up -d

    log "All services deployed successfully."
fi
