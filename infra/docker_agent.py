#!/usr/bin/env python3
"""Docker control agent — bridges the admin API to Docker Compose.

Runs as a lightweight sidecar container with Docker socket access.
Subscribes to Redis channel 'admin:docker:commands' and executes
scale/restart operations, publishing results to 'admin:docker:results'.

Also reports container status every 10s to 'admin:docker:status'.

Usage:
    python infra/docker_agent.py

Environment:
    COMPOSE_DIR  — path to docker-compose directory (default: same as script)
    REDIS_URL    — Redis connection URL
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    import redis.asyncio as aioredis
except ImportError:
    print("ERROR: redis[hiredis] required. pip install redis", file=sys.stderr)
    sys.exit(1)


COMPOSE_DIR = Path(os.environ.get("COMPOSE_DIR", str(Path(__file__).resolve().parent)))
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
CMD_CHANNEL = "admin:docker:commands"
RESULT_CHANNEL = "admin:docker:results"
STATUS_KEY = "admin:docker:status"
STATUS_TTL = 30


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(REDIS_URL, decode_responses=True, socket_timeout=None)


async def run_docker_compose(*args: str) -> dict[str, Any]:
    cmd = ["docker", "compose", *args]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(COMPOSE_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:2000],
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "error": "timeout", "success": False}
    except Exception as exc:
        return {"returncode": -1, "error": str(exc), "success": False}


async def handle_scale(params: dict) -> dict:
    service = params.get("service", "")
    replicas = params.get("replicas", 1)
    if not service:
        return {"error": "missing service name", "success": False}

    result = await run_docker_compose("up", "-d", f"--scale={service}={replicas}", service)
    return {
        "action": "scale",
        "service": service,
        "replicas": replicas,
        "success": result["success"],
        "details": result,
    }


async def handle_restart(params: dict) -> dict:
    service = params.get("service")
    if service and service != "all":
        result = await run_docker_compose("restart", service)
        return {"action": "restart", "service": service, "success": result["success"], "details": result}

    result = await run_docker_compose("restart")
    return {"action": "restart", "service": "all", "success": result["success"], "details": result}


async def handle_restart_workers(params: dict) -> dict:
    worker_services = [
        "worker-scraping-bulk", "worker-scraping-realtime", "worker-enrichment",
        "worker-maintenance", "worker-cover-bulk", "worker-cover-ranking",
        "worker-cover-generation", "worker-cover-workflow", "worker-email",
        "worker-cover-batch", "beat",
    ]
    results = {}
    for svc in worker_services:
        r = await run_docker_compose("restart", svc)
        results[svc] = r["success"]
        await asyncio.sleep(2)
    return {"action": "restart_workers", "results": results, "success": all(results.values())}


async def handle_status(params: dict) -> dict:
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=str(COMPOSE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return {"error": result.stderr[:500]}

        services: dict[str, list[dict]] = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                container = json.loads(line)
                name = container.get("Service", container.get("service", "unknown"))
                if name not in services:
                    services[name] = []
                services[name].append({
                    "id": container.get("ID", ""),
                    "state": container.get("State", ""),
                    "health": container.get("Health", ""),
                    "status": container.get("Status", ""),
                })
            except json.JSONDecodeError:
                continue
        return services
    except Exception as exc:
        return {"error": str(exc)}


HANDLERS = {
    "scale": handle_scale,
    "restart": handle_restart,
    "restart_workers": handle_restart_workers,
    "status": handle_status,
}


async def process_command(r: aioredis.Redis, message: dict) -> None:
    cmd_id = message.get("id", str(time.time()))
    action = message.get("action", "")
    params = message.get("params", {})

    handler = HANDLERS.get(action)
    if not handler:
        result = {"id": cmd_id, "action": action, "error": f"unknown action: {action}", "success": False}
    else:
        result = await handler(params)
        result["id"] = cmd_id
        result["action"] = action

    await r.publish(RESULT_CHANNEL, json.dumps(result))


async def report_status(r: aioredis.Redis) -> None:
    status = await handle_status({})
    await r.set(STATUS_KEY, json.dumps(status), ex=STATUS_TTL)


async def main() -> None:
    print(f"Docker agent starting")
    print(f"  Compose dir: {COMPOSE_DIR}")
    print(f"  Redis: {REDIS_URL.split('@')[-1] if '@' in REDIS_URL else REDIS_URL}")

    status_task: asyncio.Task | None = None

    while True:
        r = None
        pubsub = None
        try:
            r = await get_redis()
            pubsub = r.pubsub()
            await pubsub.subscribe(CMD_CHANNEL)

            if status_task and not status_task.done():
                status_task.cancel()
            status_task = asyncio.create_task(_status_loop(r))

            print("  Listening for commands...")
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    payload = json.loads(message["data"])
                    print(f"  Command: {payload.get('action')} (id={payload.get('id')})")
                    await process_command(r, payload)
                except Exception as exc:
                    print(f"  Error processing command: {exc}", file=sys.stderr)
        except (aioredis.ConnectionError, aioredis.TimeoutError, OSError) as exc:
            print(f"  Redis connection lost: {exc}. Reconnecting in 5s...", file=sys.stderr)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"  Unexpected error: {exc}. Reconnecting in 5s...", file=sys.stderr)
        finally:
            if status_task and not status_task.done():
                status_task.cancel()
            if pubsub:
                try:
                    await pubsub.unsubscribe()
                    await pubsub.aclose()
                except Exception:
                    pass
            if r:
                try:
                    await r.aclose()
                except Exception:
                    pass

        await asyncio.sleep(5)


async def _status_loop(r: aioredis.Redis) -> None:
    while True:
        try:
            await report_status(r)
        except Exception:
            pass
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
