#!/usr/bin/env bash
# Tail logs for one or all docker compose services
# Usage: bash infra/scripts/tail_logs.sh [SERVICE] [LINES]
#
# Examples:
#   bash infra/scripts/tail_logs.sh                    # follow all logs
#   bash infra/scripts/tail_logs.sh api                # follow api logs
#   bash infra/scripts/tail_logs.sh api 50             # last 50 lines, no follow
#   bash infra/scripts/tail_logs.sh worker-email 100

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

SERVICE="${1:-}"
LINES="${2:-}"

if [[ -n "$LINES" ]]; then
    # Non-follow mode: print N lines and exit
    if [[ -n "$SERVICE" ]]; then
        $COMPOSE logs --tail="$LINES" --no-log-prefix "$SERVICE"
    else
        $COMPOSE logs --tail="$LINES"
    fi
else
    # Follow mode
    if [[ -n "$SERVICE" ]]; then
        $COMPOSE logs -f --tail=50 "$SERVICE"
    else
        $COMPOSE logs -f --tail=20
    fi
fi
