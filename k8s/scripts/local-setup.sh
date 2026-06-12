#!/usr/bin/env bash
# local-setup.sh — One-shot local Kubernetes deployment using k3d + KEDA
#
# Requirements: k3d, kubectl, docker (OrbStack), brew
# Usage: bash k8s/scripts/local-setup.sh [--skip-build] [--skip-infra] [--skip-migrations]
#
# Flags:
#   --skip-build       Skip docker image build+push (use if images already in registry)
#   --skip-infra       Skip infrastructure StatefulSets (postgres/rabbitmq/redis/ollama)
#   --skip-migrations  Skip alembic migration job
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────────
CLUSTER_NAME="jh-local"
REGISTRY_NAME="k3d-jh-registry"
REGISTRY_PORT="5050"
REGISTRY_HOST="k3d-jh-registry:5050"
NS="job-hunter"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="$REPO_ROOT/k8s"
ENV_FILE="$REPO_ROOT/infra/.env"

SKIP_BUILD=false
SKIP_INFRA=false
SKIP_MIGRATIONS=false
for arg in "$@"; do
  [[ "$arg" == "--skip-build" ]] && SKIP_BUILD=true
  [[ "$arg" == "--skip-infra" ]] && SKIP_INFRA=true
  [[ "$arg" == "--skip-migrations" ]] && SKIP_MIGRATIONS=true
done

# ── Helpers ──────────────────────────────────────────────────────────────────
log()  { echo ""; echo "▶ $(date '+%H:%M:%S') $*"; }
ok()   { echo "  ✓ $*"; }
info() { echo "  · $*"; }
fail() { echo ""; echo "✗ ERROR: $*" >&2; exit 1; }

K="kubectl -n $NS"

# Apply a manifest file with local image substitution
apply_local() {
  local file="$1"
  sed \
    -e "s|ghcr.io/CHANGE_ME/jh-api:latest|${REGISTRY_HOST}/jh-api:local|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-worker-playwright:latest|${REGISTRY_HOST}/jh-worker-playwright:local|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-worker-lightweight:latest|${REGISTRY_HOST}/jh-worker-lightweight:local|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-dashboard:latest|${REGISTRY_HOST}/jh-dashboard:local|g" \
    "$file" | kubectl apply -f -
}

# ── Step 1: Preflight ────────────────────────────────────────────────────────
log "Step 1 — Preflight checks"
for tool in k3d kubectl docker; do
  command -v "$tool" &>/dev/null || fail "$tool not found. Install it first."
  ok "$tool found"
done
[[ -f "$ENV_FILE" ]] || fail "infra/.env not found at $ENV_FILE"
ok "infra/.env found"

# ── Step 2: Install Helm ─────────────────────────────────────────────────────
log "Step 2 — Helm"
if ! command -v helm &>/dev/null; then
  info "Installing Helm via brew..."
  brew install helm
  ok "Helm installed"
else
  ok "Helm already installed ($(helm version --short 2>/dev/null || echo 'version unknown'))"
fi

# ── Step 3: k3d registry ─────────────────────────────────────────────────────
log "Step 3 — k3d local registry"
REGISTRY_LIST="$(k3d registry list 2>/dev/null || true)"  # capture first (see SIGPIPE note below)
if grep -q "$REGISTRY_NAME" <<<"$REGISTRY_LIST"; then
  ok "Registry $REGISTRY_NAME already exists"
else
  info "Creating k3d registry on port $REGISTRY_PORT..."
  k3d registry create jh-registry --port "$REGISTRY_PORT"
  ok "Registry created: $REGISTRY_HOST"
fi

# ── Step 4: k3d cluster ──────────────────────────────────────────────────────
log "Step 4 — k3d cluster ($CLUSTER_NAME)"
# NOTE: capture into a var first — piping `k3d cluster list` directly into
# `grep -q` makes grep close the pipe on first match, k3d then dies with SIGPIPE
# (exit 141), and `set -o pipefail` propagates that, wrongly taking the else branch.
CLUSTER_LIST="$(k3d cluster list 2>/dev/null || true)"
if grep -q "$CLUSTER_NAME" <<<"$CLUSTER_LIST"; then
  ok "Cluster $CLUSTER_NAME already exists"
  k3d kubeconfig merge "$CLUSTER_NAME" --kubeconfig-merge-default &>/dev/null
  kubectl config use-context "k3d-$CLUSTER_NAME" &>/dev/null
else
  info "Creating k3d cluster (this takes ~30s)..."
  k3d cluster create "$CLUSTER_NAME" \
    --registry-use "$REGISTRY_NAME:$REGISTRY_PORT" \
    --port "8080:80@loadbalancer" \
    --port "15672:15672@loadbalancer" \
    --port "8001:8000@loadbalancer" \
    --k3s-arg "--disable=traefik@server:0" \
    --wait
  # Install nginx ingress (simpler than Traefik CRDs for local)
  info "Installing nginx ingress controller..."
  kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.0/deploy/static/provider/cloud/deploy.yaml &>/dev/null || true
  ok "Cluster $CLUSTER_NAME created"
fi

# ── Step 5: Build images ──────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" ]]; then
  log "Step 5 — Build Docker images (from repo root: $REPO_ROOT)"
  cd "$REPO_ROOT"

  # Extract admin API key for dashboard build arg
  ADMIN_KEY=$(grep '^NEXT_PUBLIC_ADMIN_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "local-dev-key")

  info "Building jh-api:local..."
  docker build -f infra/Dockerfile.api \
    -t "localhost:$REGISTRY_PORT/jh-api:local" \
    . --quiet && ok "jh-api built"

  info "Building jh-worker-lightweight:local..."
  docker build -f infra/Dockerfile.worker.lightweight \
    -t "localhost:$REGISTRY_PORT/jh-worker-lightweight:local" \
    . --quiet && ok "jh-worker-lightweight built"

  info "Building jh-worker-playwright:local (large image, may take several minutes)..."
  docker build -f infra/Dockerfile.worker \
    -t "localhost:$REGISTRY_PORT/jh-worker-playwright:local" \
    . --quiet && ok "jh-worker-playwright built"

  info "Building jh-dashboard:local..."
  docker build -f infra/Dockerfile.dashboard \
    --build-arg "NEXT_PUBLIC_ADMIN_API_KEY=${ADMIN_KEY}" \
    -t "localhost:$REGISTRY_PORT/jh-dashboard:local" \
    . --quiet && ok "jh-dashboard built"

  log "Step 5b — Push images to local registry"
  for img in jh-api jh-worker-lightweight jh-worker-playwright jh-dashboard; do
    info "Pushing ${img}:local..."
    docker push "localhost:$REGISTRY_PORT/${img}:local" --quiet && ok "${img} pushed"
  done
else
  ok "Skipping image build (--skip-build)"
fi

# ── Step 6: Namespace + ConfigMap ────────────────────────────────────────────
log "Step 6 — Namespace and ConfigMap"
kubectl apply -f "$K8S_DIR/namespace.yaml"
$K apply -f "$K8S_DIR/configmaps/app-config.yaml"
ok "Namespace $NS and ConfigMap applied"

# ── Step 7: Secrets from infra/.env ──────────────────────────────────────────
log "Step 7 — Kubernetes Secret from infra/.env"

# Strip comments, blank lines, and keys already governed by ConfigMap.
# ConfigMap wins for these — including them in the Secret would cause the
# Secret (applied after ConfigMap in envFrom) to override with .env values.
TMPENV=$(mktemp)
grep -v '^#' "$ENV_FILE" | grep -v '^[[:space:]]*$' | grep '=' | \
  grep -v '^LOG_TO_FILE=' | \
  grep -v '^LOG_DIR=' | \
  grep -v '^LOG_ROTATION_MB=' | \
  grep -v '^ENVIRONMENT=' > "$TMPENV" || true

# Add keys required by our manifests but not directly in .env
RMQ_URL=$(grep '^RABBITMQ_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "amqp://jobhunter:jobhunter@rabbitmq:5672/")
RMQ_PASS=$(echo "$RMQ_URL" | sed 's|amqp[s]*://[^:]*:\([^@]*\)@.*|\1|' || echo "jobhunter")
RMQ_USER=$(echo "$RMQ_URL" | sed 's|amqp[s]*://\([^:]*\):.*|\1|' || echo "jobhunter")

DB_URL=$(grep '^DATABASE_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' | tr -d "'" || echo "")
DB_PASS=$(echo "$DB_URL" | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|' || echo "jobhunter")

# Add the derived keys if not already present
grep -q '^RABBITMQ_DEFAULT_PASS=' "$TMPENV" || echo "RABBITMQ_DEFAULT_PASS=${RMQ_PASS}" >> "$TMPENV"
grep -q '^POSTGRES_PASSWORD=' "$TMPENV" || echo "POSTGRES_PASSWORD=${DB_PASS}" >> "$TMPENV"
grep -q '^RABBITMQ_DEFAULT_USER=' "$TMPENV" || echo "RABBITMQ_DEFAULT_USER=${RMQ_USER}" >> "$TMPENV"
grep -q '^POSTGRES_USER=' "$TMPENV" || echo "POSTGRES_USER=jobhunter" >> "$TMPENV"
grep -q '^POSTGRES_DB=' "$TMPENV" || echo "POSTGRES_DB=jobhunter" >> "$TMPENV"

kubectl create secret generic job-hunter-secrets \
  --namespace "$NS" \
  --from-env-file="$TMPENV" \
  --dry-run=client -o yaml | kubectl apply -f -
rm -f "$TMPENV"
ok "Secret job-hunter-secrets created from infra/.env"

# ── Step 8: KEDA ─────────────────────────────────────────────────────────────
log "Step 8 — KEDA"
if helm status keda -n keda &>/dev/null 2>&1; then
  ok "KEDA already installed"
else
  info "Adding kedacore Helm repo..."
  helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true
  helm repo update --fail-on-repo-update-fail 2>/dev/null || helm repo update || true
  info "Installing KEDA (may take 1-2 min)..."
  helm install keda kedacore/keda \
    --namespace keda \
    --create-namespace \
    --wait \
    --timeout 3m
  ok "KEDA installed"
fi

# KEDA RabbitMQ auth secret (HTTP management API)
kubectl create secret generic rabbitmq-keda-secret \
  --namespace "$NS" \
  --from-literal="host=http://${RMQ_USER}:${RMQ_PASS}@rabbitmq.${NS}.svc.cluster.local:15672/" \
  --dry-run=client -o yaml | kubectl apply -f -
$K apply -f "$K8S_DIR/keda/keda-auth-rabbitmq.yaml"
ok "KEDA TriggerAuthentication applied"

# ── Step 9: Infrastructure ───────────────────────────────────────────────────
if [[ "$SKIP_INFRA" == "false" ]]; then
  log "Step 9 — Infrastructure (postgres, rabbitmq, redis)"
  # Apply postgres, rabbitmq, redis — skip ollama to save time locally
  $K apply -f "$K8S_DIR/infrastructure/postgres.yaml"
  $K apply -f "$K8S_DIR/infrastructure/rabbitmq.yaml"
  $K apply -f "$K8S_DIR/infrastructure/redis.yaml"

  info "Waiting for postgres StatefulSet..."
  $K rollout status statefulset/postgres --timeout=120s
  info "Waiting for rabbitmq StatefulSet..."
  $K rollout status statefulset/rabbitmq --timeout=120s
  info "Waiting for redis StatefulSet..."
  $K rollout status statefulset/redis --timeout=120s
  ok "Infrastructure ready"

  # Ollama is optional locally — it's heavy. Apply but don't wait.
  info "Applying ollama (background — pull nomic-embed-text manually after setup)..."
  # Strip initContainers for local (no auto-pull — do it manually via exec)
  sed '/initContainers:/,/containers:/{ /initContainers:/d; /- name: model-pull/,/resources:/{ /resources:/! d }; }' \
    "$K8S_DIR/infrastructure/ollama.yaml" | $K apply -f - 2>/dev/null || \
    $K apply -f "$K8S_DIR/infrastructure/ollama.yaml" || true
  ok "Ollama applied (pull model manually: kubectl exec -n $NS deploy/ollama -- ollama pull nomic-embed-text)"
else
  ok "Skipping infrastructure (--skip-infra)"
fi

# ── Step 10: Migrations ───────────────────────────────────────────────────────
if [[ "$SKIP_MIGRATIONS" == "false" ]]; then
  log "Step 10 — Alembic migrations"
  $K delete job alembic-migrations --ignore-not-found=true
  apply_local "$K8S_DIR/app/migrations-job.yaml"
  info "Waiting for migrations (up to 5 min)..."
  kubectl wait --for=condition=complete job/alembic-migrations \
    -n "$NS" --timeout=300s \
    || { echo "  ⚠ Migrations timed out — check: kubectl logs job/alembic-migrations -n $NS"; }
  ok "Migrations complete"
else
  ok "Skipping migrations (--skip-migrations)"
fi

# ── Step 11: Application ──────────────────────────────────────────────────────
log "Step 11 — Application (api, dashboard, beat)"
apply_local "$K8S_DIR/app/api.yaml"
apply_local "$K8S_DIR/app/dashboard.yaml"
apply_local "$K8S_DIR/app/beat.yaml"

info "Waiting for api rollout..."
$K rollout status deployment/api --timeout=120s
info "Waiting for dashboard rollout..."
$K rollout status deployment/dashboard --timeout=120s
ok "API and Dashboard ready"

# ── Step 12: Workers ──────────────────────────────────────────────────────────
log "Step 12 — Workers + KEDA ScaledObjects"
for f in "$K8S_DIR/workers/"*.yaml; do
  apply_local "$f"
done
ok "All workers and ScaledObjects applied"

# ── Final status ──────────────────────────────────────────────────────────────
log "Deployment complete!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Job Hunter — Local Kubernetes Deployment Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
kubectl get pods -n "$NS" --sort-by=.metadata.name
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Access URLs (via port-forward):"
echo "    API:          kubectl port-forward svc/api 8001:8000 -n $NS"
echo "                  → http://localhost:8001/health"
echo "    Dashboard:    kubectl port-forward svc/dashboard 3001:3000 -n $NS"
echo "                  → http://localhost:3001"
echo "    RabbitMQ UI:  http://localhost:15672 (${RMQ_USER} / ${RMQ_PASS})"
echo ""
echo "  Monitoring scripts:"
echo "    bash k8s/scripts/worker-status.sh --watch"
echo "    bash k8s/scripts/queue-status.sh"
echo "    bash k8s/scripts/scale-check.sh"
echo ""
echo "  MCP tools (kubectl_tools):"
echo "    python mcp/admin_server.py"
echo "    → get_pod_status(), get_keda_status(), get_worker_logs()"
echo ""
echo "  Teardown:"
echo "    bash k8s/scripts/local-teardown.sh"
echo ""
