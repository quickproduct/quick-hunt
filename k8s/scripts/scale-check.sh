#!/usr/bin/env bash
# Show KEDA autoscaling state — current vs desired replicas, active triggers.
# Usage: bash k8s/scripts/scale-check.sh [--watch]
#
# To manually pause/resume KEDA scaling for a worker:
#   Pause:  kubectl annotate scaledobject worker-cover-generation-scaler \
#             autoscaling.keda.sh/paused=true --overwrite -n job-hunter
#   Resume: kubectl annotate scaledobject worker-cover-generation-scaler \
#             autoscaling.keda.sh/paused- --overwrite -n job-hunter
set -euo pipefail
NS="job-hunter"

WATCH=false
[[ "${1:-}" == "--watch" ]] && WATCH=true

show_keda() {
  echo ""
  echo "=== KEDA ScaledObject Details ($(date '+%H:%M:%S')) ==="

  # Check if any ScaledObjects exist
  local count
  count=$(kubectl get scaledobject -n "$NS" --no-headers 2>/dev/null | wc -l)
  if [[ "$count" -eq 0 ]]; then
    echo "No ScaledObjects found. Apply workers first: kubectl apply -f k8s/workers/ -n $NS"
    return
  fi

  # Wide view with min/max
  kubectl get scaledobject -n "$NS" -o wide 2>/dev/null

  echo ""
  echo "=== Current vs Desired Replicas ==="
  while IFS= read -r name; do
    local current desired min max
    current=$(kubectl get deployment "$name" -n "$NS" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "?")
    desired=$(kubectl get deployment "$name" -n "$NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
    min=$(kubectl get scaledobject "${name}-scaler" -n "$NS" -o jsonpath='{.spec.minReplicaCount}' 2>/dev/null || echo "?")
    max=$(kubectl get scaledobject "${name}-scaler" -n "$NS" -o jsonpath='{.spec.maxReplicaCount}' 2>/dev/null || echo "?")
    printf "  %-35s  ready=%s  desired=%s  min=%s  max=%s\n" "$name" "$current" "$desired" "$min" "$max"
  done < <(kubectl get scaledobject -n "$NS" -o jsonpath='{.items[*].spec.scaleTargetRef.name}' | tr ' ' '\n' | sort)

  echo ""
  echo "=== Fixed-replica deployments (no KEDA) ==="
  for dep in beat worker-cover-batch; do
    local replicas
    replicas=$(kubectl get deployment "$dep" -n "$NS" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "not found")
    printf "  %-35s  replicas=%s\n" "$dep" "$replicas"
  done
}

if [[ "$WATCH" == "true" ]]; then
  while true; do
    clear
    show_keda
    sleep 10
  done
else
  show_keda
fi
