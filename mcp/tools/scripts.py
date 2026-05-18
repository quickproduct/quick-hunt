"""
MCP tools for running shell scripts in infra/scripts/.

All scripts are executed from a fixed whitelist — no arbitrary shell access.
Destructive operations require confirm=True.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from ._base import track_duration, clamp

SCRIPTS_DIR = Path(__file__).parents[2] / "infra" / "scripts"

# Script registry: name → {desc, args_hint, destructive}
SCRIPTS: dict[str, dict[str, Any]] = {
    "quick_start": {
        "desc": "Start the full docker stack (all services + workers). Pass '--with-data' to also run migrations.",
        "args_hint": "[--with-data]",
        "destructive": False,
    },
    "quick_stop": {
        "desc": "Stop the stack gracefully. Pass '--clean' to also wipe volumes (DESTRUCTIVE).",
        "args_hint": "[--clean]",
        "destructive": True,
    },
    "quick_restart": {
        "desc": "Restart one service or all services.",
        "args_hint": "[SERVICE_NAME]",
        "destructive": False,
    },
    "deploy_update": {
        "desc": "Pull latest images, rebuild, and redeploy a service (or all).",
        "args_hint": "[SERVICE_NAME]",
        "destructive": False,
    },
    "run_migration": {
        "desc": "Apply pending Alembic DB migrations. Pass '--create MSG' to generate a new one.",
        "args_hint": "[--create MESSAGE]",
        "destructive": False,
    },
    "scale_worker": {
        "desc": "Scale a Celery worker to the given replica count.",
        "args_hint": "WORKER_NAME REPLICAS",
        "destructive": False,
    },
    "health_check": {
        "desc": "Check health of all services: API, Redis, RabbitMQ, PostgreSQL, tunnel.",
        "args_hint": "",
        "destructive": False,
    },
    "tail_logs": {
        "desc": "Print recent log lines for a service (non-follow). Usage: tail_logs SERVICE LINES.",
        "args_hint": "[SERVICE] [LINES]",
        "destructive": False,
    },
    "env_check": {
        "desc": "Validate all required environment variables are set in infra/.env.",
        "args_hint": "",
        "destructive": False,
    },
    "cleanup_logs": {
        "desc": "Remove log files older than N days from backend/logs/ (default 7 days).",
        "args_hint": "[DAYS]",
        "destructive": True,
    },
    "tunnel_start": {
        "desc": "Start a Cloudflare quick tunnel pointing to the API (default port 8001).",
        "args_hint": "[API_PORT]",
        "destructive": False,
    },
    "tunnel_status": {
        "desc": "Show cloudflared process count, current webhook URL, and recent monitor logs.",
        "args_hint": "",
        "destructive": False,
    },
    "tunnel_monitor": {
        "desc": "Run the tunnel health-check/restart cycle (normally run via cron).",
        "args_hint": "",
        "destructive": False,
    },
    "db_backup": {
        "desc": "Take an immediate PostgreSQL backup to infra/backups/. Keeps last 7 days.",
        "args_hint": "",
        "destructive": False,
    },
    "kibana_import": {
        "desc": "Import Job Hunter saved objects (index patterns, saved searches) into Kibana.",
        "args_hint": "",
        "destructive": False,
    },
}

DESTRUCTIVE_SCRIPTS = {name for name, meta in SCRIPTS.items() if meta["destructive"]}


async def _run_script(name: str, args: list[str] = [], timeout: int = 60) -> tuple[int, str]:
    """Execute a whitelisted script, return (returncode, combined output)."""
    script_path = SCRIPTS_DIR / f"{name}.sh"
    cmd = ["bash", str(script_path)] + args

    # Pass current env plus SCRIPTS_DIR so scripts can locate each other
    env = {**os.environ, "JH_SCRIPTS_DIR": str(SCRIPTS_DIR)}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        cwd=str(SCRIPTS_DIR),
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return -1, f"Script '{name}' timed out after {timeout}s"

    output = stdout.decode("utf-8", errors="replace").strip()
    return proc.returncode or 0, output


def _fmt_result(name: str, returncode: int, output: str) -> str:
    return json.dumps(
        {
            "script": name,
            "returncode": returncode,
            "success": returncode == 0,
            "output": output,
        },
        indent=2,
    )


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def list_scripts() -> str:
        """
        List all available shell scripts with descriptions and argument hints.
        Scripts in infra/scripts/ that can be run via run_script() or their
        dedicated shortcut tools.
        """
        lines = []
        for name in sorted(SCRIPTS):
            meta = SCRIPTS[name]
            tag = " [destructive]" if meta["destructive"] else ""
            args = f"  args: {meta['args_hint']}" if meta["args_hint"] else ""
            lines.append(f"{name}{tag}\n    {meta['desc']}{args}")
        return "Available scripts:\n\n" + "\n\n".join(lines)

    @mcp.tool()
    @track_duration
    async def run_script(name: str, args: str = "", confirm: bool = False) -> str:
        """
        Run a named script from infra/scripts/.

        name:    script name without .sh extension (see list_scripts)
        args:    space-separated arguments string passed to the script
        confirm: required for destructive scripts (quick_stop --clean, cleanup_logs)
        """
        name = name.strip().lower().replace(".sh", "")
        if name not in SCRIPTS:
            available = ", ".join(sorted(SCRIPTS))
            return json.dumps({"error": f"Unknown script '{name}'", "available": available})

        if name in DESTRUCTIVE_SCRIPTS and not confirm:
            return json.dumps(
                {
                    "error": f"Script '{name}' is destructive — set confirm=True to proceed.",
                    "hint": "Call list_scripts() to review what it does first.",
                }
            )

        arg_list = args.split() if args.strip() else []
        returncode, output = await _run_script(name, arg_list)
        return _fmt_result(name, returncode, output)

    # ------------------------------------------------------------------ #
    # Shortcut tools for common operations                               #
    # ------------------------------------------------------------------ #

    @mcp.tool()
    @track_duration
    async def quick_start(with_data: bool = False) -> str:
        """
        Start the full AI Job Hunter docker stack.

        with_data: if True, starts infra services first, runs DB migrations,
                   then starts application services.
        """
        args = ["--with-data"] if with_data else []
        returncode, output = await _run_script("quick_start", args, timeout=120)
        return _fmt_result("quick_start", returncode, output)

    @mcp.tool()
    @track_duration
    async def quick_stop(clean: bool = False, confirm: bool = False) -> str:
        """
        Stop the AI Job Hunter docker stack.

        clean:   if True, also removes volumes — DESTRUCTIVE, wipes database data
        confirm: must be True when clean=True
        """
        if clean and not confirm:
            return json.dumps(
                {"error": "clean=True removes all volumes including the database. Set confirm=True to proceed."}
            )
        args = ["--clean"] if clean else []
        returncode, output = await _run_script("quick_stop", args, timeout=60)
        return _fmt_result("quick_stop", returncode, output)

    @mcp.tool()
    @track_duration
    async def restart_service(service: str = "") -> str:
        """
        Restart a specific docker compose service or all services.

        service: service name (e.g. 'api', 'worker-email'). Leave empty to restart all.
        """
        args = [service] if service.strip() else []
        returncode, output = await _run_script("quick_restart", args, timeout=60)
        return _fmt_result("quick_restart", returncode, output)

    @mcp.tool()
    @track_duration
    async def deploy_service(service: str = "") -> str:
        """
        Pull the latest image, rebuild, and redeploy a service (or all services).

        service: service name (e.g. 'api', 'dashboard'). Leave empty to rebuild all.
        """
        args = [service] if service.strip() else []
        returncode, output = await _run_script("deploy_update", args, timeout=300)
        return _fmt_result("deploy_update", returncode, output)

    @mcp.tool()
    @track_duration
    async def get_service_logs(service: str, lines: int = 100) -> str:
        """
        Return recent log lines for a docker compose service.

        service: service name, e.g. 'api', 'worker-email', 'postgres'
        lines:   number of lines to return, 1-500
        """
        if not service.strip():
            return json.dumps({"error": "service name is required"})
        lines = clamp(lines, 1, 500)
        returncode, output = await _run_script("tail_logs", [service, str(lines)], timeout=15)
        return _fmt_result("tail_logs", returncode, output)

    @mcp.tool()
    @track_duration
    async def run_migration(create_message: str = "") -> str:
        """
        Apply pending Alembic database migrations, or generate a new migration file.

        create_message: if provided, generates a new autogenerated migration with this message
                        instead of applying pending migrations.
        """
        if create_message.strip():
            args = ["--create", create_message.strip()]
        else:
            args = []
        returncode, output = await _run_script("run_migration", args, timeout=60)
        return _fmt_result("run_migration", returncode, output)

    @mcp.tool()
    @track_duration
    async def backup_database(confirm: bool = False) -> str:
        """
        Trigger an immediate PostgreSQL backup to infra/backups/.
        Backups older than 7 days are automatically removed.

        confirm: must be True to proceed (protects against accidental calls)
        """
        if not confirm:
            return json.dumps({"error": "Set confirm=True to trigger a database backup."})
        returncode, output = await _run_script("db_backup", [], timeout=120)
        return _fmt_result("db_backup", returncode, output)

    @mcp.tool()
    @track_duration
    async def scale_worker_script(worker: str, replicas: int, confirm: bool = False) -> str:
        """
        Scale a Celery worker to the given number of replicas via docker compose.

        worker:   worker service name, e.g. 'worker-cover-generation', 'worker-scraping-bulk'
        replicas: target replica count (0 = pause the worker)
        confirm:  must be True to proceed
        """
        valid_workers = [
            "worker-scraping-bulk", "worker-scraping-realtime", "worker-enrichment",
            "worker-maintenance", "worker-cover-bulk", "worker-cover-ranking",
            "worker-cover-generation", "worker-cover-workflow", "worker-email", "worker-agentic",
        ]
        if worker not in valid_workers:
            return json.dumps(
                {"error": f"Unknown worker '{worker}'", "valid_workers": valid_workers}
            )
        if replicas < 0:
            return json.dumps({"error": "replicas must be >= 0"})
        if not confirm:
            return json.dumps(
                {"error": f"Set confirm=True to scale {worker} to {replicas} replica(s)."}
            )
        returncode, output = await _run_script("scale_worker", [worker, str(replicas)], timeout=60)
        return _fmt_result("scale_worker", returncode, output)

    @mcp.tool()
    @track_duration
    async def check_system_health() -> str:
        """
        Run a full health check across all services: docker containers, API,
        Redis, RabbitMQ, PostgreSQL, and Cloudflare tunnel.
        """
        returncode, output = await _run_script("health_check", [], timeout=30)
        return _fmt_result("health_check", returncode, output)

    @mcp.tool()
    @track_duration
    async def check_env_vars() -> str:
        """
        Validate that all required environment variables are set in infra/.env.
        Reports which are missing or empty.
        """
        returncode, output = await _run_script("env_check", [], timeout=10)
        return _fmt_result("env_check", returncode, output)

    @mcp.tool()
    @track_duration
    async def check_tunnel_status() -> str:
        """
        Show the Cloudflare tunnel status: running processes, current webhook URL,
        and the last few lines of the monitor log.
        """
        returncode, output = await _run_script("tunnel_status", [], timeout=10)
        return _fmt_result("tunnel_status", returncode, output)

    @mcp.tool()
    @track_duration
    async def start_tunnel(api_port: int = 8001) -> str:
        """
        Start a Cloudflare quick tunnel pointing to the local API server.
        Writes the tunnel URL to /tmp/current_webhook_url.

        api_port: local port the API is listening on (default 8001)
        """
        api_port = clamp(api_port, 1, 65535)
        returncode, output = await _run_script("tunnel_start", [str(api_port)], timeout=60)
        return _fmt_result("tunnel_start", returncode, output)

    @mcp.tool()
    @track_duration
    async def cleanup_old_logs(days: int = 7, confirm: bool = False) -> str:
        """
        Remove log files older than N days from backend/logs/ and rotate
        the tunnel monitor log if it exceeds 10MB.

        days:    retention window in days (default 7)
        confirm: must be True to proceed
        """
        if not confirm:
            return json.dumps(
                {"error": f"Set confirm=True to delete log files older than {days} days."}
            )
        days = clamp(days, 1, 365)
        returncode, output = await _run_script("cleanup_logs", [str(days)], timeout=30)
        return _fmt_result("cleanup_logs", returncode, output)
