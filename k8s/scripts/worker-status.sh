#!/usr/bin/env bash
# Show pod status, KEDA ScaledObject state, and replica counts for all workers.
# Usage: bash k8s/scripts/worker-status.sh [--watch]
set -euo pipefail
NS="job-hunter"

WATCH=false
[[ "${1:-}" == "--watch" ]] && WATCH=true

show_status() {
  echo ""
  echo "=== Pod Status ($(date '+%H:%M:%S')) ==="
  kubectl get pods -n "$NS" \
    -o custom-columns="NAME:.metadata.name,STATUS:.status.phase,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount,NODE:.spec.nodeName" \
    --sort-by='.metadata.name'

  echo ""
  echo "=== KEDA ScaledObjects ==="
  kubectl get scaledobject -n "$NS" \
    -o custom-columns="NAME:.metadata.name,MIN:.spec.minReplicaCount,MAX:.spec.maxReplicaCount,READY:.status.conditions[0].status,ACTIVE:.status.conditions[1].status" \
    2>/dev/null || echo "(No ScaledObjects found — KEDA may not be installed yet)"

  echo ""
  echo "=== Deployment Replicas ==="
  kubectl get deployments -n "$NS" \
    -o custom-columns="DEPLOYMENT:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,AVAILABLE:.status.availableReplicas" \
    --sort-by='.metadata.name'

  echo ""
  echo "=== Resource Usage (requires metrics-server) ==="
  kubectl top pods -n "$NS" --sort-by=memory 2>/dev/null || echo "(metrics-server not available)"
}

if [[ "$WATCH" == "true" ]]; then
  while true; do
    clear
    show_status
    sleep 10
  done
else
  show_status
fi
