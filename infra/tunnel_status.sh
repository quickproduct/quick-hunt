#!/bin/bash
# Quick status check for tunnel and webhook

echo "=== Tunnel Status ==="
ps aux | grep cloudflared | grep -v grep | wc -l | xargs -I {} echo "Processes: {}"

echo ""
echo "=== Current Webhook URL ==="
cat /tmp/current_brevo_webhook_url 2>/dev/null || echo "Not available"

echo ""
echo "=== Recent Monitor Logs ==="
tail -5 /tmp/tunnel_monitor.log 2>/dev/null || echo "No logs yet"

echo ""
echo "=== Cron Job ==="
crontab -l | grep tunnel_monitor 2>/dev/null || echo "Not installed"
