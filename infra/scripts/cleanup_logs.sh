#!/usr/bin/env bash
# Remove log files older than N days from backend/logs/
# Usage: bash infra/scripts/cleanup_logs.sh [DAYS]
#
# Default retention: 7 days
# Also cleans /tmp/tunnel_monitor.log if it exceeds 10MB

set -euo pipefail

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPTS_DIR/../.." && pwd)"
LOGS_DIR="$PROJECT_DIR/backend/logs"
DAYS="${1:-7}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== Log Cleanup — retaining last $DAYS days ==="

# Backend logs
if [[ -d "$LOGS_DIR" ]]; then
    COUNT=$(find "$LOGS_DIR" -type f -mtime +"$DAYS" | wc -l | tr -d ' ')
    if [[ "$COUNT" -gt 0 ]]; then
        find "$LOGS_DIR" -type f -mtime +"$DAYS" -delete
        log "Deleted $COUNT log file(s) from $LOGS_DIR"
    else
        log "No log files older than $DAYS days in $LOGS_DIR"
    fi
else
    log "WARN: $LOGS_DIR does not exist, skipping."
fi

# Tunnel monitor log rotation (keep under 10MB)
TUNNEL_LOG="/tmp/tunnel_monitor.log"
if [[ -f "$TUNNEL_LOG" ]]; then
    SIZE=$(du -k "$TUNNEL_LOG" | cut -f1)
    if [[ "$SIZE" -gt 10240 ]]; then
        tail -500 "$TUNNEL_LOG" > "${TUNNEL_LOG}.tmp" && mv "${TUNNEL_LOG}.tmp" "$TUNNEL_LOG"
        log "Rotated $TUNNEL_LOG (was ${SIZE}KB, kept last 500 lines)"
    else
        log "$TUNNEL_LOG is ${SIZE}KB — no rotation needed"
    fi
fi

log "=== Cleanup complete ==="
