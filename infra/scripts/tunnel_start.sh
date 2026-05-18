#!/usr/bin/env bash
# Start a Cloudflare quick tunnel pointing to the API
# Usage: bash infra/scripts/tunnel_start.sh [API_PORT]
#
# Default API port: 8001
# The tunnel URL is written to /tmp/current_webhook_url once established.

set -euo pipefail

API_PORT="${1:-8001}"
TUNNEL_LOG="/tmp/cloudflared.log"
WEBHOOK_URL_FILE="/tmp/current_webhook_url"
BREVO_SECRET="${BREVO_WEBHOOK_SECRET:-}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# Check cloudflared is available
if ! command -v cloudflared &>/dev/null; then
    echo "ERROR: cloudflared not found. Install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/"
    exit 1
fi

# Kill any existing tunnel
if pgrep -f "cloudflared tunnel" > /dev/null; then
    log "Stopping existing cloudflared tunnel..."
    pkill -f "cloudflared tunnel" 2>/dev/null || true
    sleep 2
fi

log "Starting Cloudflare tunnel → http://localhost:$API_PORT"
rm -f "$TUNNEL_LOG"
cloudflared tunnel --url "http://localhost:$API_PORT" > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!
echo "$TUNNEL_PID" > /tmp/cloudflared.pid
log "cloudflared PID: $TUNNEL_PID"

# Wait for URL to appear in log
log "Waiting for tunnel URL (up to 30s)..."
TIMEOUT=30
ELAPSED=0
while [[ $ELAPSED -lt $TIMEOUT ]]; do
    if grep -q "trycloudflare.com" "$TUNNEL_LOG" 2>/dev/null; then
        break
    fi
    sleep 2
    ELAPSED=$((ELAPSED + 2))
done

TUNNEL_URL=$(grep -o "https://[a-z-]*\.trycloudflare\.com" "$TUNNEL_LOG" 2>/dev/null | tail -1 || true)

if [[ -z "$TUNNEL_URL" ]]; then
    log "ERROR: Could not extract tunnel URL after ${TIMEOUT}s"
    cat "$TUNNEL_LOG" 2>/dev/null || true
    exit 1
fi

echo "$TUNNEL_URL" > "$WEBHOOK_URL_FILE"
log "Tunnel URL: $TUNNEL_URL"

if [[ -n "$BREVO_SECRET" ]]; then
    WEBHOOK="${TUNNEL_URL}/webhooks/brevo?secret=${BREVO_SECRET}"
    echo "$WEBHOOK" > "/tmp/current_brevo_webhook_url"
    log "Brevo webhook URL: $WEBHOOK"
fi

log "Tunnel running in background (PID $TUNNEL_PID). Logs: $TUNNEL_LOG"
