#!/usr/bin/env bash
# Query RabbitMQ queue depths directly via kubectl exec into the rabbitmq pod.
# Shows: queue name, message count, consumer count, memory usage.
# Usage: bash k8s/scripts/queue-status.sh [--watch]
set -euo pipefail
NS="job-hunter"

WATCH=false
[[ "${1:-}" == "--watch" ]] && WATCH=true

get_rmq_pod() {
  kubectl get pod -n "$NS" -l app=rabbitmq -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

show_queues() {
  local pod
  pod=$(get_rmq_pod) || { echo "No RabbitMQ pod found in namespace $NS"; return 1; }

  echo ""
  echo "=== RabbitMQ Queue Status ($(date '+%H:%M:%S')) ==="
  kubectl exec -n "$NS" "$pod" -- \
    rabbitmqctl list_queues \
      name messages messages_ready messages_unacknowledged consumers memory \
      --formatter pretty_table 2>/dev/null \
    | grep -E "^(name|jh_)" || echo "No job-hunter queues found yet (workers haven't registered)"

  echo ""
  echo "=== RabbitMQ Node Overview ==="
  kubectl exec -n "$NS" "$pod" -- \
    rabbitmqctl status 2>/dev/null \
    | grep -E "(Memory|Disk|Uptime|Running)" | head -10 || true
}

if [[ "$WATCH" == "true" ]]; then
  while true; do
    clear
    show_queues
    sleep 15
  done
else
  show_queues
fi
