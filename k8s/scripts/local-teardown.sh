#!/usr/bin/env bash
# local-teardown.sh — Delete the local k3d cluster and registry
# Usage: bash k8s/scripts/local-teardown.sh [--keep-registry]
set -euo pipefail

CLUSTER_NAME="jh-local"
REGISTRY_NAME="k3d-jh-registry"
KEEP_REGISTRY=false
[[ "${1:-}" == "--keep-registry" ]] && KEEP_REGISTRY=true

echo "▶ Deleting k3d cluster: $CLUSTER_NAME"
k3d cluster delete "$CLUSTER_NAME" 2>/dev/null && echo "  ✓ Cluster deleted" || echo "  · Cluster not found (already deleted?)"

if [[ "$KEEP_REGISTRY" == "false" ]]; then
  echo "▶ Deleting k3d registry: $REGISTRY_NAME"
  k3d registry delete "$REGISTRY_NAME" 2>/dev/null && echo "  ✓ Registry deleted" || echo "  · Registry not found"
fi

echo ""
echo "✓ Local k3d environment cleaned up."
