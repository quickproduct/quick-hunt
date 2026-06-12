import asyncio
import sys
import os
from mcp.server.fastmcp import FastMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import (
    K8S_NAMESPACE, K8S_PORT_FORWARDS,
    KEDA_SCALABLE_WORKERS, ALLOWED_K8S_DEPLOYMENTS,
)
from ._base import track_duration, clamp, validate_choice

# ── Background port-forward process registry ──────────────────────────────────
_port_forwards: dict = {}


async def _kubectl(*args: str, timeout: int = 30) -> str:
    cmd = ["kubectl", "-n", K8S_NAMESPACE, *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"kubectl timed out after {timeout}s")
    if proc.returncode != 0:
        raise RuntimeError(
            stderr.decode(errors="replace").strip()
            or f"kubectl exited {proc.returncode}"
        )
    return stdout.decode(errors="replace").strip()


# ── Dynamic worker/deployment discovery ───────────────────────────────────────
# The static sets in config.py drifted from the cluster (consulting/mnc/detail
# workers were missing), which made newer workers invisible to these tools and
# masked a real outage. Discover live names from the cluster instead, falling
# back to the static sets only when kubectl is unavailable.
_discovery_cache: dict[str, tuple[float, set[str]]] = {}
_DISCOVERY_TTL_SECONDS = 60.0


async def _discover_names(kind: str) -> set[str]:
    import time
    now = time.monotonic()
    cached = _discovery_cache.get(kind)
    if cached and now - cached[0] < _DISCOVERY_TTL_SECONDS:
        return cached[1]
    out = await _kubectl("get", kind, "-o", "name", timeout=10)
    names = {line.split("/", 1)[1] for line in out.splitlines() if "/" in line}
    if names:
        _discovery_cache[kind] = (now, names)
    return names


async def get_allowed_deployments() -> set[str]:
    try:
        return await _discover_names("deployments") or ALLOWED_K8S_DEPLOYMENTS
    except Exception:
        return ALLOWED_K8S_DEPLOYMENTS


async def get_scalable_workers() -> set[str]:
    """Workers with a KEDA ScaledObject (named '<worker>-scaler' by convention)."""
    try:
        scalers = await _discover_names("scaledobjects")
        if scalers:
            return {s.removesuffix("-scaler") for s in scalers if s.endswith("-scaler")}
    except Exception:
        pass
    return KEDA_SCALABLE_WORKERS


def register(mcp: FastMCP) -> None:

    # ── Pod / cluster status ──────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def get_pod_status() -> str:
        """
        List all pods in the job-hunter namespace with status, readiness, restart
        count, and node. Equivalent to 'kubectl get pods -o wide'.
        """
        try:
            return await _kubectl("get", "pods", "-o", "wide", "--sort-by=.metadata.name")
        except RuntimeError as exc:
            return f"Error: {exc}"

    @mcp.tool()
    @track_duration
    async def get_cluster_summary() -> str:
        """
        Full one-shot cluster health overview: pod status, KEDA ScaledObjects,
        resource usage, and recent warnings — all fetched concurrently.
        Use this as the first diagnostic command when something seems wrong.
        """
        pods, keda, resources, events = await asyncio.gather(
            _kubectl("get", "pods", "-o", "wide", "--sort-by=.metadata.name"),
            _kubectl("get", "scaledobject", "-o", "wide"),
            _kubectl("top", "pods", "--sort-by=memory"),
            _kubectl("get", "events", "--sort-by=.lastTimestamp", "--field-selector=type=Warning"),
            return_exceptions=True,
        )
        sections = [
            "═══ PODS ═══",
            pods if isinstance(pods, str) else f"Error: {pods}",
            "\n═══ KEDA SCALED OBJECTS ═══",
            keda if isinstance(keda, str) else f"Error: {keda}",
            "\n═══ RESOURCE USAGE ═══",
            resources if isinstance(resources, str) else f"Error (metrics-server): {resources}",
            "\n═══ RECENT WARNINGS ═══",
            (events if isinstance(events, str) else f"Error: {events}") or "No warnings.",
        ]
        return "\n".join(sections)

    @mcp.tool()
    @track_duration
    async def get_keda_status() -> str:
        """
        Show KEDA ScaledObject status — min/max replicas, ready state, and active
        trigger status for each autoscaled worker.
        """
        try:
            return await _kubectl("get", "scaledobject", "-o", "wide")
        except RuntimeError as exc:
            return f"Error: {exc}"

    @mcp.tool()
    @track_duration
    async def get_resource_usage() -> str:
        """
        Show live CPU and memory usage per pod, sorted by memory descending.
        Requires metrics-server (included in k3s by default).
        """
        try:
            return await _kubectl("top", "pods", "--sort-by=memory")
        except RuntimeError as exc:
            return f"Error (metrics-server may not be available): {exc}"

    @mcp.tool()
    @track_duration
    async def describe_failed_pods() -> str:
        """
        Find pods not in Running or Succeeded phase and return their describe output.
        Useful for diagnosing CrashLoopBackOff, OOMKilled, or Pending pods.
        """
        try:
            raw = await _kubectl(
                "get", "pods",
                "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.phase}\\n{end}",
            )
        except RuntimeError as exc:
            return f"Error listing pods: {exc}"

        failed = []
        for line in raw.splitlines():
            if "=" not in line:
                continue
            name, phase = line.split("=", 1)
            if phase not in ("Running", "Succeeded", ""):
                try:
                    desc = await _kubectl("describe", "pod", name.strip(), timeout=10)
                    failed.append(f"=== {name.strip()} (phase={phase}) ===\n{desc}")
                except RuntimeError:
                    failed.append(f"=== {name.strip()} (phase={phase}) — could not describe ===")

        return "\n\n".join(failed) if failed else "All pods are Running or Succeeded."

    # ── Logs ──────────────────────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def get_worker_logs(deployment: str, lines: int = 50, previous: bool = False) -> str:
        """
        Tail logs from the most recent pod of a deployment.

        deployment: one of the allowed deployment names, e.g. 'worker-cover-generation',
                    'api', 'beat', 'worker-scraping-bulk'
        lines:      number of tail lines, 1-200 (default: 50)
        previous:   if True, fetch logs from the previous (crashed) container —
                    essential for diagnosing CrashLoopBackOff root cause

        Allowed: any deployment currently in the namespace (discovered live via
                 kubectl; includes consulting/mnc/detail workers).
        """
        deployment = deployment.strip().lower()
        err = validate_choice(deployment, await get_allowed_deployments(), "deployment")
        if err:
            return err
        lines = clamp(lines, 1, 200)
        flags = ["logs", f"deployment/{deployment}", f"--tail={lines}", "--timestamps=true"]
        if previous:
            flags.append("--previous")
        try:
            return await _kubectl(*flags, timeout=20)
        except RuntimeError as exc:
            return f"Error fetching logs for '{deployment}': {exc}"

    @mcp.tool()
    @track_duration
    async def get_all_pod_logs(lines: int = 20) -> str:
        """
        Fetch logs concurrently from every Running pod — one block per pod.
        Useful for a full-cluster snapshot to spot errors at a glance.

        lines: tail lines per pod, 1-50 (default: 20)
        """
        lines = clamp(lines, 1, 50)
        try:
            raw = await _kubectl(
                "get", "pods",
                "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.phase}\\n{end}",
            )
        except RuntimeError as exc:
            return f"Error listing pods: {exc}"

        running = [
            line.split("=", 1)[0].strip()
            for line in raw.splitlines()
            if "=" in line and line.split("=", 1)[1] == "Running"
        ]
        if not running:
            return "No Running pods found."

        async def _pod_logs(pod: str) -> str:
            try:
                out = await _kubectl("logs", pod, f"--tail={lines}", "--timestamps=true", timeout=15)
                return f"=== {pod} ===\n{out or '(no output)'}"
            except RuntimeError as exc:
                return f"=== {pod} ===\nError: {exc}"

        results = await asyncio.gather(*[_pod_logs(p) for p in running])
        return "\n\n".join(results)  # type: ignore[arg-type]

    # ── KEDA control ──────────────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def describe_keda_scaler(worker: str) -> str:
        """
        Show detailed KEDA ScaledObject info: trigger configuration, current/desired
        replicas, and condition messages explaining why KEDA is or isn't scaling.

        worker: e.g. 'worker-cover-generation', 'worker-scraping-realtime'
        """
        worker = worker.strip().lower()
        err = validate_choice(worker, await get_scalable_workers(), "worker")
        if err:
            return err
        try:
            return await _kubectl("describe", "scaledobject", f"{worker}-scaler", timeout=10)
        except RuntimeError as exc:
            return f"Error describing '{worker}-scaler': {exc}"

    @mcp.tool()
    @track_duration
    async def pause_keda_scaling(worker: str) -> str:
        """
        Pause KEDA autoscaling for a worker. The deployment stays at its current
        replica count until resumed. Useful during deployments or investigations.

        worker: e.g. 'worker-cover-generation', 'worker-scraping-bulk'

        Note: cover-batch and beat are not KEDA-managed — no ScaledObject to pause.
        """
        worker = worker.strip().lower()
        err = validate_choice(worker, await get_scalable_workers(), "worker")
        if err:
            return err
        scaler = f"{worker}-scaler"
        try:
            out = await _kubectl(
                "annotate", "scaledobject", scaler,
                "autoscaling.keda.sh/paused=true", "--overwrite",
            )
            return f"KEDA scaling paused for '{worker}' (ScaledObject: {scaler})." + (f"\n{out}" if out else "")
        except RuntimeError as exc:
            return f"Error pausing scaling for '{worker}': {exc}"

    @mcp.tool()
    @track_duration
    async def resume_keda_scaling(worker: str) -> str:
        """
        Resume KEDA autoscaling for a previously paused worker.

        worker: e.g. 'worker-cover-generation', 'worker-scraping-bulk'
        """
        worker = worker.strip().lower()
        err = validate_choice(worker, await get_scalable_workers(), "worker")
        if err:
            return err
        scaler = f"{worker}-scaler"
        try:
            out = await _kubectl(
                "annotate", "scaledobject", scaler,
                "autoscaling.keda.sh/paused-", "--overwrite",
            )
            return f"KEDA scaling resumed for '{worker}'." + (f"\n{out}" if out else "")
        except RuntimeError as exc:
            return f"Error resuming scaling for '{worker}': {exc}"

    # ── Deployment control ────────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def rollout_restart(deployment: str) -> str:
        """
        Perform a rolling restart of a deployment (graceful — waits for running
        tasks to finish before replacing pods due to terminationGracePeriodSeconds).

        deployment: e.g. 'api', 'worker-cover-generation', 'beat'
        """
        deployment = deployment.strip().lower()
        err = validate_choice(deployment, await get_allowed_deployments(), "deployment")
        if err:
            return err
        try:
            out = await _kubectl("rollout", "restart", f"deployment/{deployment}", timeout=15)
            return f"Rolling restart triggered for '{deployment}'." + (f"\n{out}" if out else "")
        except RuntimeError as exc:
            return f"Error restarting '{deployment}': {exc}"

    @mcp.tool()
    @track_duration
    async def scale_deployment(deployment: str, replicas: int) -> str:
        """
        Manually set the replica count for a deployment.

        deployment: e.g. 'worker-cover-generation', 'api'
        replicas:   0–10 (KEDA-managed workers will revert after cooldownPeriod)

        Useful for: scaling a worker to 0 to drain its queue handler, or boosting
        replicas beyond KEDA's current target for a burst.
        """
        deployment = deployment.strip().lower()
        err = validate_choice(deployment, await get_allowed_deployments(), "deployment")
        if err:
            return err
        replicas = clamp(replicas, 0, 10)
        try:
            await _kubectl("scale", f"deployment/{deployment}", f"--replicas={replicas}", timeout=15)
            return f"Scaled '{deployment}' to {replicas} replica(s)."
        except RuntimeError as exc:
            return f"Error scaling '{deployment}': {exc}"

    @mcp.tool()
    @track_duration
    async def force_delete_pod(pod_name: str) -> str:
        """
        Force-delete a stuck or terminating pod immediately (grace period = 0).
        Kubernetes will reschedule a replacement automatically.

        pod_name: exact pod name from get_pod_status(), e.g.
                  'worker-cover-generation-7b9599df96-rztkf'

        WARNING: any in-flight task will be interrupted but requeued by RabbitMQ
        (task_acks_late=True). Use only for pods stuck in Terminating or repeated
        CrashLoopBackOff that won't self-recover.
        """
        pod_name = pod_name.strip()
        if not pod_name or "/" in pod_name:
            return "Error: provide an exact pod name (not a deployment name). Get it from get_pod_status()."
        try:
            out = await _kubectl("delete", "pod", pod_name, "--grace-period=0", "--force", timeout=20)
            return f"Force-deleted pod '{pod_name}'.\n{out}"
        except RuntimeError as exc:
            return f"Error force-deleting '{pod_name}': {exc}"

    # ── Events ────────────────────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def get_deployment_events(deployment: str) -> str:
        """
        Show recent Kubernetes events for a deployment AND its pods.
        Catches scheduling failures, image pull errors, OOM kills, liveness probe
        failures — anything Kubernetes emitted about this workload.

        deployment: e.g. 'worker-cover-generation', 'api'
        """
        deployment = deployment.strip().lower()
        err = validate_choice(deployment, await get_allowed_deployments(), "deployment")
        if err:
            return err

        dep_events, pod_raw = await asyncio.gather(
            _kubectl("get", "events",
                     "--field-selector", f"involvedObject.name={deployment}",
                     "--sort-by=.lastTimestamp"),
            _kubectl("get", "pods", "-l", f"app={deployment}",
                     "-o", "jsonpath={range .items[*]}{.metadata.name}\\n{end}"),
            return_exceptions=True,
        )

        sections = [f"=== Deployment events: {deployment} ==="]
        sections.append(dep_events if isinstance(dep_events, str) else f"Error: {dep_events}")
        sections.append("(none)" if isinstance(dep_events, str) and not dep_events else "")

        if isinstance(pod_raw, str):
            for pod in (p.strip() for p in pod_raw.splitlines() if p.strip()):
                try:
                    pod_ev = await _kubectl(
                        "get", "events",
                        "--field-selector", f"involvedObject.name={pod}",
                        "--sort-by=.lastTimestamp",
                        timeout=10,
                    )
                    sections.append(f"\n=== Pod events: {pod} ===")
                    sections.append(pod_ev or "(none)")
                except RuntimeError as exc:
                    sections.append(f"\n=== Pod events: {pod} ===\nError: {exc}")

        return "\n".join(sections)

    # ── RabbitMQ queue depths ─────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def get_queue_depths() -> str:
        """
        Show RabbitMQ business queue depths and consumer counts via rabbitmqctl —
        no port-forward needed. Shows only jh_* queues, sorted by depth (deepest first).

        Use this to: check scraping progress, spot backlogs, understand why KEDA
        is scaling a particular worker.
        """
        cmd = [
            "kubectl", "exec", "-n", K8S_NAMESPACE, "rabbitmq-0", "--",
            "rabbitmqctl", "list_queues", "name", "messages", "consumers",
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                return f"Error: {stderr.decode(errors='replace').strip()}"
        except asyncio.TimeoutError:
            return "Error: rabbitmqctl timed out after 30s"

        rows = []
        for line in stdout.decode(errors="replace").splitlines():
            parts = line.split()
            if len(parts) == 3 and parts[0].startswith("jh_"):
                try:
                    rows.append((parts[0], int(parts[1]), int(parts[2])))
                except ValueError:
                    pass
        rows.sort(key=lambda r: r[1], reverse=True)

        if not rows:
            return "No jh_* queues found. Is RabbitMQ running?"

        header = f"{'Queue':<45} {'Messages':>8} {'Consumers':>9}"
        divider = "-" * len(header)
        lines = [header, divider]
        for name, msgs, consumers in rows:
            flag = " ◀ BACKLOG" if msgs > 50 else (" ◀ active" if msgs > 0 else "")
            lines.append(f"{name:<45} {msgs:>8} {consumers:>9}{flag}")
        return "\n".join(lines)

    # ── Port forwarding ───────────────────────────────────────────────────────

    @mcp.tool()
    @track_duration
    async def get_port_forward_status() -> str:
        """
        Show status of all MCP-managed port-forwards: running state and access URLs.
        Call start_port_forwards() to start them.
        """
        lines = [f"{'Service':<12} {'Status':<30} {'Access URL'}"]
        lines.append("-" * 75)
        for name, (target, local_port, remote_port, url) in K8S_PORT_FORWARDS.items():
            proc = _port_forwards.get(name)
            if proc is None:
                status = "not started"
            elif proc.returncode is None:
                status = f"running (pid={proc.pid})"
            else:
                status = f"exited({proc.returncode}) — call start_port_forwards()"
            lines.append(f"{name:<12} {status:<30} {url}")
        return "\n".join(lines)

    @mcp.tool()
    @track_duration
    async def start_port_forwards(services: str = "all") -> str:
        """
        Start kubectl port-forward background processes so cluster services are
        reachable from localhost without manual terminal commands.

        services: comma-separated names or "all" (default)
                  Available: api, dashboard, rabbitmq, postgres, redis, ollama

        Port assignments (chosen to avoid host conflicts):
          api       → http://localhost:8002
          dashboard → http://localhost:3001
          rabbitmq  → http://localhost:15673  (login: jobhunter / jobhunter)
          postgres  → localhost:5433          (user=jobhunter db=jobhunter)
          redis     → localhost:6380
          ollama    → http://localhost:11435

        Processes live as long as the MCP server runs and are auto-cleaned on exit.
        Verify with get_port_forward_status().
        """
        targets = (
            list(K8S_PORT_FORWARDS.keys())
            if services.strip().lower() == "all"
            else [s.strip().lower() for s in services.split(",")]
        )

        results = []
        for name in targets:
            if name not in K8S_PORT_FORWARDS:
                results.append(f"{name}: unknown (available: {', '.join(K8S_PORT_FORWARDS)})")
                continue

            target, local_port, remote_port, url = K8S_PORT_FORWARDS[name]

            existing = _port_forwards.get(name)
            if existing is not None and existing.returncode is None:
                results.append(f"{name}: already running → {url}")
                continue

            proc = await asyncio.create_subprocess_exec(
                "kubectl", "-n", K8S_NAMESPACE,
                "port-forward", target, f"{local_port}:{remote_port}",
                "--address=127.0.0.1",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            _port_forwards[name] = proc
            results.append(f"{name}: started (pid={proc.pid}) → {url}")

        await asyncio.sleep(1)  # let processes bind before caller checks
        return "\n".join(results)

    @mcp.tool()
    @track_duration
    async def stop_port_forwards(services: str = "all") -> str:
        """
        Stop MCP-managed port-forward processes.

        services: comma-separated names or "all" (default)
                  Available: api, dashboard, rabbitmq, postgres, redis, ollama
        """
        targets = (
            list(K8S_PORT_FORWARDS.keys())
            if services.strip().lower() == "all"
            else [s.strip().lower() for s in services.split(",")]
        )

        results = []
        for name in targets:
            proc = _port_forwards.pop(name, None)
            if proc is None or proc.returncode is not None:
                results.append(f"{name}: not running")
                continue
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
            results.append(f"{name}: stopped")

        return "\n".join(results)
