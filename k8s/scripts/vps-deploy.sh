#!/usr/bin/env bash
# Build and redeploy AI Job Hunter on a single-node K3s VPS.
#
# This script assumes K3s is using its default containerd runtime. Images are
# built with Docker, imported into K3s containerd, then applied with a fresh
# git-SHA tag so Kubernetes rolls pods onto the latest code.
#
# Usage:
#   bash k8s/scripts/vps-deploy.sh
#
# Optional env:
#   SKIP_INFRA=true bash k8s/scripts/vps-deploy.sh
#   SKIP_MIGRATIONS=true bash k8s/scripts/vps-deploy.sh
#   FORCE_RESTART=true bash k8s/scripts/vps-deploy.sh  # same SHA, env-only change

set -euo pipefail

NS="${NS:-job-hunter}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="$REPO_ROOT/k8s"
ENV_FILE="${ENV_FILE:-$REPO_ROOT/infra/.env}"
IMAGE_PREFIX="${IMAGE_PREFIX:-job-hunter}"
IMAGE_TAG="${IMAGE_TAG:-$(git -C "$REPO_ROOT" rev-parse --short HEAD)}"
SKIP_INFRA="${SKIP_INFRA:-false}"
SKIP_MIGRATIONS="${SKIP_MIGRATIONS:-false}"
FORCE_RESTART="${FORCE_RESTART:-false}"

K="kubectl -n $NS"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
die() { echo "ERROR: $*" >&2; exit 1; }

require_tools() {
  for tool in docker k3s kubectl helm git sed grep python3; do
    command -v "$tool" >/dev/null 2>&1 || die "$tool is not installed or not on PATH"
  done

  [[ -f "$ENV_FILE" ]] || die "$ENV_FILE is missing. Create it on the VPS before deploying."
}

env_value() {
  local key="$1"
  grep -E "^${key}=" "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'" || true
}

validate_env() {
  local key value
  for key in ADMIN_API_KEY SECRET_KEY DATABASE_URL RABBITMQ_URL; do
    value="$(env_value "$key")"
    [[ -n "$value" ]] || die "$key is required in $ENV_FILE"
    if [[ "$value" == *CHANGE_ME* || "$value" == *change-me* || "$value" == your_generated_* ]]; then
      die "$key still contains a placeholder value"
    fi
  done

  value="$(env_value INITIAL_ADMIN_PASSWORD)"
  if [[ -n "$value" ]]; then
    [[ "$value" != *CHANGE_ME* && "$value" != *change-me* ]] || \
      die "INITIAL_ADMIN_PASSWORD still contains a placeholder value"
    [[ ${#value} -ge 16 ]] || die "INITIAL_ADMIN_PASSWORD must be at least 16 characters"
  fi
}

cleanup_stale_terminating_api_pods() {
  kubectl get namespace "$NS" >/dev/null 2>&1 || return 0

  local minimum_age_seconds="${1:-300}"
  local now pod deleted_at deleted_epoch age_seconds
  now="$(date +%s)"
  while IFS=$'\t' read -r pod deleted_at; do
    [[ -n "$pod" && -n "$deleted_at" ]] || continue
    deleted_epoch="$(date -d "$deleted_at" +%s 2>/dev/null || echo 0)"
    [[ "$deleted_epoch" -gt 0 ]] || continue
    age_seconds=$((now - deleted_epoch))
    if [[ "$age_seconds" -ge "$minimum_age_seconds" ]]; then
      log "Force-removing stale terminating API pod $pod (terminating for ${age_seconds}s)..."
      $K delete pod "$pod" --grace-period=0 --force --wait=false
    fi
  done < <(
    # Go templates emit every matching pod reliably across kubectl versions;
    # the loop above ignores pods that do not have a deletion timestamp.
    $K get pods -l app=api \
      -o go-template='{{range .items}}{{.metadata.name}}{{"\t"}}{{.metadata.deletionTimestamp}}{{"\n"}}{{end}}'
  )
}

cleanup_superseded_api_pods() {
  local target_image="${IMAGE_PREFIX}/jh-api:${IMAGE_TAG}"
  local pod image
  while IFS=$'\t' read -r pod image; do
    [[ -n "$pod" && -n "$image" ]] || continue
    if [[ "$image" != "$target_image" ]]; then
      log "Force-removing superseded API pod $pod running $image..."
      $K delete pod "$pod" --grace-period=0 --force --wait=false
    fi
  done < <(
    $K get pods -l app=api \
      -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].image}{"\n"}{end}'
  )
}

wait_for_target_api_replicas() {
  local target_image="${IMAGE_PREFIX}/jh-api:${IMAGE_TAG}"
  local desired deadline ready_count
  desired="$($K get deployment api -o jsonpath='{.spec.replicas}')"
  deadline=$((SECONDS + 120))

  while (( SECONDS < deadline )); do
    ready_count="$($K get pods -l app=api -o json | TARGET_IMAGE="$target_image" python3 -c '
import json
import os
import sys

target = os.environ["TARGET_IMAGE"]
pods = json.load(sys.stdin).get("items", [])
ready = 0
for pod in pods:
    images = [container.get("image") for container in pod.get("spec", {}).get("containers", [])]
    conditions = pod.get("status", {}).get("conditions", [])
    is_ready = any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions)
    if target in images and not pod.get("metadata", {}).get("deletionTimestamp") and is_ready:
        ready += 1
print(ready)
')"
    if [[ "${ready_count:-0}" -ge "${desired:-1}" ]]; then
      log "Target API image $target_image has ${ready_count}/${desired} Ready replicas."
      return 0
    fi
    sleep 5
  done

  $K get pods -l app=api -o wide >&2
  die "Target API image $target_image did not reach ${desired} Ready replicas."
}

create_secret_from_env() {
  log "Creating Kubernetes secrets from $ENV_FILE..."

  local tmpenv rmq_url rmq_pass rmq_user db_url db_pass
  tmpenv="$(mktemp)"
  trap 'rm -f "$tmpenv"' RETURN
  grep -v '^#' "$ENV_FILE" | grep -v '^[[:space:]]*$' | grep '=' | \
    grep -v '^LOG_TO_FILE=' | \
    grep -v '^LOG_DIR=' | \
    grep -v '^LOG_ROTATION_MB=' | \
    grep -v '^ENVIRONMENT=' > "$tmpenv" || true

  rmq_url="$(env_value RABBITMQ_URL)"
  rmq_url="${rmq_url:-amqp://jobhunter:jobhunter@rabbitmq:5672/}"
  rmq_pass="$(echo "$rmq_url" | sed 's|amqp[s]*://[^:]*:\([^@]*\)@.*|\1|')"
  rmq_user="$(echo "$rmq_url" | sed 's|amqp[s]*://\([^:]*\):.*|\1|')"

  db_url="$(env_value DATABASE_URL)"
  db_pass="$(echo "$db_url" | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|' || true)"
  db_pass="${db_pass:-jobhunter}"

  grep -q '^RABBITMQ_DEFAULT_PASS=' "$tmpenv" || echo "RABBITMQ_DEFAULT_PASS=${rmq_pass}" >> "$tmpenv"
  grep -q '^POSTGRES_PASSWORD=' "$tmpenv" || echo "POSTGRES_PASSWORD=${db_pass}" >> "$tmpenv"
  grep -q '^RABBITMQ_DEFAULT_USER=' "$tmpenv" || echo "RABBITMQ_DEFAULT_USER=${rmq_user}" >> "$tmpenv"
  grep -q '^POSTGRES_USER=' "$tmpenv" || echo "POSTGRES_USER=jobhunter" >> "$tmpenv"
  grep -q '^POSTGRES_DB=' "$tmpenv" || echo "POSTGRES_DB=jobhunter" >> "$tmpenv"

  kubectl create secret generic job-hunter-secrets \
    --namespace "$NS" \
    --from-env-file="$tmpenv" \
    --dry-run=client -o yaml | kubectl apply -f -

  kubectl create secret generic rabbitmq-keda-secret \
    --namespace "$NS" \
    --from-literal="host=http://${rmq_user}:${rmq_pass}@rabbitmq.${NS}.svc.cluster.local:15672/" \
    --dry-run=client -o yaml | kubectl apply -f -

  rm -f "$tmpenv"
  trap - RETURN
}

build_image() {
  local name="$1"
  local dockerfile="$2"
  shift 2

  log "Building ${name}:${IMAGE_TAG}..."
  docker build \
    -f "$dockerfile" \
    -t "${IMAGE_PREFIX}/${name}:${IMAGE_TAG}" \
    -t "${IMAGE_PREFIX}/${name}:latest" \
    "$@" \
    "$REPO_ROOT"
}

import_image() {
  local name="$1"
  log "Importing ${name}:${IMAGE_TAG} into K3s containerd..."
  docker save "${IMAGE_PREFIX}/${name}:${IMAGE_TAG}" "${IMAGE_PREFIX}/${name}:latest" | \
    k3s ctr --namespace k8s.io images import -
}

build_and_import_images() {
  build_image "jh-api" "$REPO_ROOT/infra/Dockerfile.api"
  build_image "jh-worker-lightweight" "$REPO_ROOT/infra/Dockerfile.worker.lightweight"
  build_image "jh-worker-playwright" "$REPO_ROOT/infra/Dockerfile.worker"
  build_image "jh-dashboard" "$REPO_ROOT/infra/Dockerfile.dashboard"

  for image in jh-api jh-worker-lightweight jh-worker-playwright jh-dashboard; do
    import_image "$image"
  done
}

render_manifest() {
  local file="$1"
  sed \
    -e "s|k3d-jh-registry:5050/jh-api:local|${IMAGE_PREFIX}/jh-api:${IMAGE_TAG}|g" \
    -e "s|k3d-jh-registry:5050/jh-worker-playwright:local|${IMAGE_PREFIX}/jh-worker-playwright:${IMAGE_TAG}|g" \
    -e "s|k3d-jh-registry:5050/jh-worker-lightweight:local|${IMAGE_PREFIX}/jh-worker-lightweight:${IMAGE_TAG}|g" \
    -e "s|k3d-jh-registry:5050/jh-dashboard:local|${IMAGE_PREFIX}/jh-dashboard:${IMAGE_TAG}|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-api:latest|${IMAGE_PREFIX}/jh-api:${IMAGE_TAG}|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-worker-playwright:latest|${IMAGE_PREFIX}/jh-worker-playwright:${IMAGE_TAG}|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-worker-lightweight:latest|${IMAGE_PREFIX}/jh-worker-lightweight:${IMAGE_TAG}|g" \
    -e "s|ghcr.io/CHANGE_ME/jh-dashboard:latest|${IMAGE_PREFIX}/jh-dashboard:${IMAGE_TAG}|g" \
    -e "s|imagePullPolicy: Always|imagePullPolicy: IfNotPresent|g" \
    "$file"
}

apply_manifest() {
  local file="$1"
  render_manifest "$file" | kubectl apply -f -
}

install_keda() {
  if helm status keda -n keda >/dev/null 2>&1; then
    log "KEDA already installed."
    return
  fi

  log "Installing KEDA..."
  helm repo add kedacore https://kedacore.github.io/charts >/dev/null 2>&1 || true
  helm repo update
  helm install keda kedacore/keda --namespace keda --create-namespace --wait --timeout 3m
}

deploy_cluster() {
  log "Applying namespace, config, and secrets..."
  kubectl apply -f "$K8S_DIR/namespace.yaml"
  $K apply -f "$K8S_DIR/configmaps/app-config.yaml"
  create_secret_from_env
  install_keda
  $K apply -f "$K8S_DIR/keda/keda-auth-rabbitmq.yaml"

  if [[ "$SKIP_INFRA" != "true" ]]; then
    log "Applying infrastructure..."
    $K apply -f "$K8S_DIR/infrastructure/postgres.yaml"
    $K apply -f "$K8S_DIR/infrastructure/rabbitmq.yaml"
    $K apply -f "$K8S_DIR/infrastructure/redis.yaml"
    $K apply -f "$K8S_DIR/infrastructure/ollama.yaml"

    $K rollout status statefulset/postgres --timeout=180s
    $K rollout status statefulset/rabbitmq --timeout=180s
    $K rollout status statefulset/redis --timeout=180s
    $K rollout status deployment/ollama --timeout=240s || true
  fi

  if [[ "$SKIP_MIGRATIONS" != "true" ]]; then
    log "Running migrations..."
    $K delete job alembic-migrations --ignore-not-found=true
    apply_manifest "$K8S_DIR/app/migrations-job.yaml"
    kubectl wait --for=condition=complete job/alembic-migrations -n "$NS" --timeout=300s
  fi

  log "Applying app deployments..."
  apply_manifest "$K8S_DIR/app/api.yaml"
  apply_manifest "$K8S_DIR/app/dashboard.yaml"
  apply_manifest "$K8S_DIR/app/beat.yaml"

  log "Applying worker deployments..."
  for file in "$K8S_DIR/workers/"*.yaml; do
    apply_manifest "$file"
  done

  # Applying a fresh git-SHA image already starts one rollout for each app and
  # worker. Starting a second rollout here can leave two generations pending
  # termination and exhaust single-node capacity. Keep an explicit escape hatch
  # for a same-SHA deployment whose only change is a refreshed environment.
  if [[ "$FORCE_RESTART" == "true" ]]; then
    log "Force-restarting deployments for a same-SHA environment-only change..."
    $K rollout restart deployment
  else
    log "Fresh SHA manifests applied; skipping redundant second rollout."
  fi

  if [[ -f "$K8S_DIR/ingress/ingress.yaml" ]]; then
    if grep -q "CHANGE_ME" "$K8S_DIR/ingress/ingress.yaml"; then
      log "Skipping ingress because k8s/ingress/ingress.yaml still has CHANGE_ME placeholders."
    else
      $K apply -f "$K8S_DIR/ingress/ingress.yaml"
    fi
  fi

  log "Waiting for core app rollouts..."
  if ! $K rollout status deployment/api --timeout=60s; then
    # Confirm the target SHA itself is Ready. Deployment.availableReplicas can
    # still refer to an old pod and is not a sufficient handoff safety check.
    wait_for_target_api_replicas
    log "Target API replacement is Ready; clearing superseded image revisions..."
    cleanup_superseded_api_pods
    wait_for_target_api_replicas
  fi
  $K rollout status deployment/dashboard --timeout=180s
  $K rollout status deployment/beat --timeout=180s

  log "Waiting for active worker rollouts..."
  local deployment desired
  while IFS= read -r deployment; do
    desired="$($K get deployment "$deployment" -o jsonpath='{.spec.replicas}')"
    if [[ "${desired:-0}" -gt 0 ]]; then
      $K rollout status "deployment/$deployment" --timeout=240s
    fi
  done < <($K get deployments -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
}

verify_cluster() {
  log "Verifying deployed revision ${IMAGE_TAG}..."

  local unhealthy pod current_errors previous_errors restart_total
  unhealthy="$($K get pods --no-headers | awk '$3 !~ /^(Running|Completed)$/ {print}')"
  if [[ -n "$unhealthy" ]]; then
    echo "$unhealthy" >&2
    die "One or more pods are not Running or Completed."
  fi

  $K exec deployment/api -- python -c \
    "import json, urllib.request; data=json.load(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=10)); assert data.get('status') in {'healthy', 'ok'}, data; print('API health:', data.get('status'))"

  log "KEDA readiness and replica ceilings:"
  $K get scaledobjects \
    -o custom-columns='NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,ACTIVE:.status.conditions[?(@.type=="Active")].status,MIN:.spec.minReplicaCount,MAX:.spec.maxReplicaCount' || true

  restart_total="$($K get pods -o jsonpath='{range .items[*]}{range .status.containerStatuses[*]}{.restartCount}{"\n"}{end}{end}' | awk '{sum += $1} END {print sum + 0}')"
  log "Current pod container restart total: $restart_total"

  log "Scanning recent pod logs for high-signal runtime failures (counts only)..."
  while IFS= read -r pod; do
    current_errors="$($K logs "$pod" --all-containers --since=15m --tail=1000 2>/dev/null | grep -Eic 'Traceback|CRITICAL|panic:|SyntaxError|ModuleNotFoundError|ImportError|UnhandledPromiseRejection|FATAL' || true)"
    previous_errors="$($K logs "$pod" --all-containers --previous --tail=500 2>/dev/null | grep -Eic 'Traceback|CRITICAL|panic:|SyntaxError|ModuleNotFoundError|ImportError|UnhandledPromiseRejection|FATAL' || true)"
    printf 'log-scan pod=%s current_high_signal=%s previous_high_signal=%s\n' \
      "$pod" "${current_errors:-0}" "${previous_errors:-0}"
  done < <($K get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
}

main() {
  cd "$REPO_ROOT"
  require_tools
  validate_env
  cleanup_stale_terminating_api_pods
  build_and_import_images
  deploy_cluster
  verify_cluster

  log "Deployment complete."
  kubectl get nodes -o wide
  kubectl get pods -n "$NS" --sort-by=.metadata.name
}

main "$@"
