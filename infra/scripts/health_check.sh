#!/usr/bin/env bash
# System health check for all AI Job Hunter services
# Usage: bash infra/scripts/health_check.sh

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPTS_DIR/.." && pwd)"
COMPOSE_FILE="$INFRA_DIR/docker-compose.yml"
ENV_FILE="$INFRA_DIR/.env"
COMPOSE="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE"

OK="[OK]"
FAIL="[FAIL]"
WARN="[WARN]"

echo "=== AI Job Hunter Health Check — $(date '+%Y-%m-%d %H:%M:%S') ==="
echo ""

# Docker containers
echo "--- Docker Containers ---"
RUNNING=$($COMPOSE ps --status running --format "{{.Name}}" 2>/dev/null | wc -l | tr -d ' ')
TOTAL=$($COMPOSE ps --format "{{.Name}}" 2>/dev/null | wc -l | tr -d ' ')
echo "  Containers running: $RUNNING / $TOTAL"
$COMPOSE ps --format "  {{.Name}}: {{.Status}}" 2>/dev/null || echo "  (docker compose not available)"

echo ""

# API health
echo "--- API ---"
API_URL="${JH_API_URL:-http://localhost:8001}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$API_URL/health" 2>/dev/null || echo "000")
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "  $OK API reachable at $API_URL (HTTP $HTTP_CODE)"
else
    echo "  $FAIL API not reachable at $API_URL (HTTP $HTTP_CODE)"
fi

echo ""

# Redis
echo "--- Redis ---"
REDIS_URL="${JH_REDIS_URL:-redis://localhost:6379/0}"
REDIS_HOST=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f1)
REDIS_PORT=$(echo "$REDIS_URL" | sed 's|redis://||' | cut -d: -f2 | cut -d/ -f1)
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_REPLY=$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null || echo "ERROR")
if [[ "$REDIS_REPLY" == "PONG" ]]; then
    echo "  $OK Redis reachable at $REDIS_HOST:$REDIS_PORT"
else
    echo "  $FAIL Redis not reachable at $REDIS_HOST:$REDIS_PORT ($REDIS_REPLY)"
fi

echo ""

# RabbitMQ
echo "--- RabbitMQ ---"
RABBITMQ_URL="${JH_RABBITMQ_URL:-http://localhost:15672}"
RABBITMQ_USER="${JH_RABBITMQ_USER:-jobhunter}"
RABBITMQ_PASS="${JH_RABBITMQ_PASS:-jobhunter}"
RMQ_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
    -u "$RABBITMQ_USER:$RABBITMQ_PASS" "$RABBITMQ_URL/api/overview" 2>/dev/null || echo "000")
if [[ "$RMQ_CODE" == "200" ]]; then
    echo "  $OK RabbitMQ management API reachable (HTTP $RMQ_CODE)"
else
    echo "  $FAIL RabbitMQ not reachable at $RABBITMQ_URL (HTTP $RMQ_CODE)"
fi

echo ""

# PostgreSQL (via docker)
echo "--- PostgreSQL ---"
PG_RESULT=$($COMPOSE exec -T postgres pg_isready -U jobhunter -d jobhunter 2>/dev/null || echo "ERROR")
if echo "$PG_RESULT" | grep -q "accepting connections"; then
    echo "  $OK PostgreSQL accepting connections"
else
    echo "  $FAIL PostgreSQL not ready ($PG_RESULT)"
fi

echo ""

# Tunnel status
echo "--- Cloudflare Tunnel ---"
TUNNEL_PROCS=$(ps aux | grep cloudflared | grep -v grep | wc -l | tr -d ' ')
if [[ "$TUNNEL_PROCS" -gt 0 ]]; then
    TUNNEL_URL=$(cat /tmp/current_webhook_url 2>/dev/null || echo "unknown")
    echo "  $OK cloudflared running ($TUNNEL_PROCS process(es)) — URL: $TUNNEL_URL"
else
    echo "  $WARN cloudflared not running (run tunnel_start.sh if needed)"
fi

echo ""
echo "=== Health check complete ==="
