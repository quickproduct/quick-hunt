#!/usr/bin/env bash
# port-forward.sh — keeps all cluster services reachable from localhost.
# Each forward runs in its own restart loop; all loops run in parallel.
# Kill this script (Ctrl-C or kill <pid>) to stop everything.

NS="job-hunter"
PIDS=()

forward() {
  local name=$1 target=$2 local_port=$3 remote_port=$4
  while true; do
    echo "[port-forward] starting $name → localhost:$local_port"
    kubectl -n "$NS" port-forward "$target" "${local_port}:${remote_port}" --address=127.0.0.1
    echo "[port-forward] $name exited (code $?), restarting in 2s..."
    sleep 2
  done
}

forward api       svc/api         8002  8000  &  PIDS+=($!)
forward dashboard svc/dashboard   3001  3000  &  PIDS+=($!)
forward rabbitmq  pod/rabbitmq-0  15673 15672 &  PIDS+=($!)
forward postgres  pod/postgres-0  5433  5432  &  PIDS+=($!)
forward redis     pod/redis-0     6380  6379  &  PIDS+=($!)
forward ollama    svc/ollama      11435 11434 &  PIDS+=($!)

trap 'echo "Stopping port-forwards..."; kill "${PIDS[@]}" 2>/dev/null; wait; exit 0' INT TERM

echo "[port-forward] all 6 forwards started. PIDs: ${PIDS[*]}"
wait
