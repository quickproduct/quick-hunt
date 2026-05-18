#!/bin/bash
# Tunnel Monitor - Keeps Cloudflare tunnel alive and updates webhook URL
# Run every 5 minutes via cron

set -euo pipefail

# Configuration
TUNNEL_LOG="/tmp/cloudflared.log"
WEBHOOK_URL_FILE="/tmp/current_webhook_url"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BREVO_SECRET="${BREVO_WEBHOOK_SECRET:?BREVO_WEBHOOK_SECRET env var is required}"
API_PORT="8001"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> /tmp/tunnel_monitor.log
}

# Check if cloudflared is running
check_tunnel_process() {
    if pgrep -f "cloudflared tunnel" > /dev/null; then
        log "Cloudflare tunnel process found running"
        return 0
    else
        log "Cloudflare tunnel process not found"
        return 1
    fi
}

# Extract tunnel URL from log
get_tunnel_url() {
    if [[ -f "$TUNNEL_LOG" ]]; then
        grep -o "https://[a-z-]*\.trycloudflare\.com" "$TUNNEL_LOG" 2>/dev/null | tail -1
    fi
}

# Test tunnel connectivity
test_tunnel() {
    local url="$1"
    if curl -s --max-time 10 "$url/health" | grep -q "status.*ok"; then
        log "Tunnel connectivity test passed: $url"
        return 0
    else
        log "Tunnel connectivity test failed: $url"
        return 1
    fi
}

# Restart tunnel
restart_tunnel() {
    log "Restarting Cloudflare tunnel..."
    
    # Kill existing processes
    pkill -9 -f cloudflared 2>/dev/null || true
    sleep 2
    
    # Clean old logs
    rm -f "$TUNNEL_LOG"
    
    # Start new tunnel
    cloudflared tunnel --url "http://localhost:$API_PORT" > "$TUNNEL_LOG" 2>&1 &
    local tunnel_pid=$!
    
    # Wait for tunnel to initialize
    sleep 10
    
    # Check if process started
    if ! kill -0 "$tunnel_pid" 2>/dev/null; then
        log "Failed to start tunnel process"
        return 1
    fi
    
    # Wait for URL extraction
    local timeout=30
    local elapsed=0
    while [[ $elapsed -lt $timeout ]]; do
        if [[ -f "$TUNNEL_LOG" ]] && grep -q "trycloudflare.com" "$TUNNEL_LOG"; then
            log "Tunnel URL extracted from log"
            break
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    
    # Extract and test URL
    local new_url
    new_url=$(get_tunnel_url)
    if [[ -n "$new_url" ]]; then
        if test_tunnel "$new_url"; then
            log "Tunnel restarted successfully: $new_url"
            echo "$new_url" > "$WEBHOOK_URL_FILE"
            return 0
        fi
    fi
    
    log "Failed to restart tunnel properly"
    return 1
}

# Update webhook URL notification
notify_webhook_change() {
    local new_url="$1"
    local webhook_url="${new_url}/webhooks/brevo?secret=${BREVO_SECRET}"
    
    log "NEW WEBHOOK URL: $webhook_url"
    
    # Create/update a file with the current webhook URL for easy reference
    echo "$webhook_url" > "/tmp/current_brevo_webhook_url"
    
    # Optional: Send notification (uncomment if you want desktop notification)
    # if command -v osascript > /dev/null; then
    #     osascript -e "display notification \"Tunnel URL updated\" with title \"AI Job Hunter\" subtitle \"$webhook_url\""
    # fi
    
    # Update project README with new URL (optional)
    # sed -i.bak "s|https://[a-z-]*\.trycloudflare\.com|$new_url|g" "$PROJECT_DIR/README.md" 2>/dev/null || true
}

# Main execution
main() {
    log "=== Tunnel Monitor Check Started ==="
    
    # Check if tunnel is running
    if check_tunnel_process; then
        # Get current URL and test it
        current_url=$(get_tunnel_url)
        if [[ -n "$current_url" ]] && test_tunnel "$current_url"; then
            log "Tunnel is healthy: $current_url"
            echo "$current_url" > "$WEBHOOK_URL_FILE"
        else
            log "Tunnel process exists but not responding, restarting..."
            if restart_tunnel; then
                new_url=$(get_tunnel_url)
                if [[ -n "$new_url" ]]; then
                    notify_webhook_change "$new_url"
                fi
            fi
        fi
    else
        log "Tunnel not running, starting..."
        if restart_tunnel; then
            new_url=$(get_tunnel_url)
            if [[ -n "$new_url" ]]; then
                notify_webhook_change "$new_url"
            fi
        fi
    fi
    
    log "=== Tunnel Monitor Check Completed ==="
}

# Run main function
main "$@"
