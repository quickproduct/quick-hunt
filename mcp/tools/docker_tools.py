import asyncio
import json
import sys
import os
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, clamp, validate_choice

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import COMPOSE_FILE, ALLOWED_DOCKER_SERVICES


async def _compose_async(*args: str, timeout: int = 30) -> str:
    cmd = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError(f"docker compose timed out after {timeout}s")
    if proc.returncode != 0:
        raise RuntimeError(
            stderr.decode(errors="replace").strip()
            or f"docker compose exited {proc.returncode}"
        )
    return stdout.decode(errors="replace").strip()


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def list_containers() -> str:
        """
        List all Docker Compose services with their current status, ports,
        and health state. Equivalent to 'docker compose ps'.
        """
        try:
            raw = await _compose_async("ps", "--format", "json")
        except RuntimeError as exc:
            return f"Error: {exc}"

        containers = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    containers.append({"raw": line})

        if not containers:
            return "No containers found. Is the stack running? Try: docker compose up -d"
        return fmt(containers)

    @mcp.tool()
    @track_duration
    async def get_docker_status() -> str:
        """
        Fetch the aggregated Docker container status from the docker-agent
        sidecar (cached in Redis). Includes per-service running/stopped state.
        """
        data = await api("GET", "/admin/docker/status", cache_ttl=10)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def restart_container(service: str) -> str:
        """
        Restart a specific Docker Compose service.

        service: container service name, e.g. 'api', 'beat', 'worker-enrichment',
                 'redis', 'rabbitmq', 'postgres', 'ollama', 'dashboard'

        Allowed services: api, beat, worker-scraping-bulk, worker-scraping-realtime,
        worker-enrichment, worker-maintenance, worker-cover-bulk, worker-cover-ranking,
        worker-cover-generation, worker-cover-workflow, worker-email, worker-cover-batch,
        dashboard, redis, rabbitmq, postgres, ollama
        """
        service = service.strip().lower()
        err = validate_choice(service, ALLOWED_DOCKER_SERVICES, "service")
        if err:
            return err
        try:
            out = await _compose_async("restart", service, timeout=60)
            return f"Restarted '{service}' successfully." + (f"\n{out}" if out else "")
        except RuntimeError as exc:
            return f"Error restarting '{service}': {exc}"

    @mcp.tool()
    @track_duration
    async def get_container_logs(service: str, lines: int = 50) -> str:
        """
        Tail the stdout/stderr logs from a specific Docker Compose service.

        service: container service name (same allowed list as restart_container)
        lines:   number of tail lines to return, 1-200 (default: 50)
        """
        service = service.strip().lower()
        err = validate_choice(service, ALLOWED_DOCKER_SERVICES, "service")
        if err:
            return err
        lines = clamp(lines, 1, 200)
        try:
            out = await _compose_async("logs", "--no-color", f"--tail={lines}", service, timeout=15)
            return out if out else f"No log output from '{service}'."
        except RuntimeError as exc:
            return f"Error fetching logs for '{service}': {exc}"
