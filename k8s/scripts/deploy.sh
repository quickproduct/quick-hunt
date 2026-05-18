#!/usr/bin/env bash
# Full cluster deployment — applies manifests in the correct order.
# Usage: bash k8s/scripts/deploy.sh [--skip-infra] [--skip-migrations]
#
# Prerequisites:
#   1. kubectl configured to point at your k3s cluster
#   2. Helm installed (https://helm.sh/docs/intro/install/)
#   3. k8s/secrets/secrets.yaml filled with real values
#   4. k8s/configmaps/app-config.yaml updated with your domain + R2 endpoint
#   5. Image tags updated in all YAML files (replace ghcr.io/CHANGE_ME/...)
set -euo pipefail

NS="job-hunter"
K="kubectl -n $NS"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K8S_DIR="$(dirname "$SCRIPT_DIR")"

SKIP_INFRA=false
SKIP_MIGRATIONS=false
for arg in "$@"; do
  [[ "$arg" == "--skip-infra" ]] && SKIP_INFRA=true
  [[ "$arg" == "--skip-migrations" ]] && SKIP_MIGRATIONS=true
done

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
ok()   { echo "[$(date '+%H:%M:%S')] ✓ $*"; }
fail() { echo "[$(date '+%H:%M:%S')] ✗ $*" >&2; exit 1; }

# --- Phase 1: Bootstrap ---
log "Phase 1 — Namespace + Config"
kubectl apply -f "$K8S_DIR/namespace.yaml"
$K apply -f "$K8S_DIR/configmaps/app-config.yaml"

# Validate secrets file has been filled in
if grep -q "CHANGE_ME" "$K8S_DIR/secrets/secrets.yaml"; then
  fail "secrets.yaml still has CHANGE_ME placeholders. Fill in real values first."
fi
$K apply -f "$K8S_DIR/secrets/secrets.yaml"

# Install KEDA via Helm if not already installed
if ! helm status keda -n keda &>/dev/null; then
  log "Installing KEDA..."
  helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true
  helm repo update
  helm install keda kedacore/keda --namespace keda --create-namespace --wait
  ok "KEDA installed"
else
  ok "KEDA already installed"
fi

# Validate KEDA secret
if grep -q "CHANGE_ME" "$K8S_DIR/keda/keda-auth-rabbitmq.yaml"; then
  fail "keda-auth-rabbitmq.yaml still has CHANGE_ME. Set the RabbitMQ password first."
fi
$K apply -f "$K8S_DIR/keda/keda-auth-rabbitmq.yaml"
ok "Phase 1 complete"

if [[ "$SKIP_INFRA" == "false" ]]; then
  # --- Phase 2: Infrastructure ---
  log "Phase 2 — Infrastructure (postgres, rabbitmq, redis, ollama)"
  $K apply -f "$K8S_DIR/infrastructure/"

  log "  Waiting for postgres..."
  $K rollout status statefulset/postgres --timeout=120s
  log "  Waiting for rabbitmq..."
  $K rollout status statefulset/rabbitmq --timeout=120s
  log "  Waiting for redis..."
  $K rollout status statefulset/redis --timeout=120s
  log "  Waiting for ollama..."
  $K rollout status deployment/ollama --timeout=180s
  ok "Phase 2 complete — infrastructure ready"
fi

if [[ "$SKIP_MIGRATIONS" == "false" ]]; then
  # --- Phase 3: Database Migrations ---
  log "Phase 3 — Alembic migrations"
  # Delete previous job if it exists (ttl may not have expired)
  $K delete job alembic-migrations --ignore-not-found=true
  $K apply -f "$K8S_DIR/app/migrations-job.yaml"  # workingDir /app, -c backend/alembic.ini
  log "  Waiting for migrations to complete (up to 5 min)..."
  kubectl wait --for=condition=complete job/alembic-migrations -n "$NS" --timeout=300s \
    || fail "Migrations failed — check: kubectl logs job/alembic-migrations -n $NS"
  ok "Phase 3 complete — migrations done"
fi

# --- Phase 4: Application ---
log "Phase 4 — Application (api, dashboard, beat)"
$K apply -f "$K8S_DIR/app/api.yaml"
$K apply -f "$K8S_DIR/app/dashboard.yaml"
$K apply -f "$K8S_DIR/app/beat.yaml"

log "  Waiting for api..."
$K rollout status deployment/api --timeout=120s
log "  Waiting for dashboard..."
$K rollout status deployment/dashboard --timeout=120s
ok "Phase 4 complete"

# --- Phase 5: Workers ---
log "Phase 5 — Workers (all 10 worker types + KEDA ScaledObjects)"
$K apply -f "$K8S_DIR/workers/"
ok "Phase 5 complete — workers + ScaledObjects applied"

# --- Phase 6: Ingress ---
log "Phase 6 — Ingress"
$K apply -f "$K8S_DIR/ingress/"
ok "Phase 6 complete"

echo ""
echo "============================================"
echo "  Deployment complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo "  1. Check pod status:     bash k8s/scripts/worker-status.sh"
echo "  2. Check queue depths:   bash k8s/scripts/queue-status.sh"
echo "  3. Watch KEDA scaling:   bash k8s/scripts/scale-check.sh"
echo "  4. Port-forward RabbitMQ mgmt UI:"
echo "     kubectl port-forward svc/rabbitmq 15672:15672 -n $NS"
