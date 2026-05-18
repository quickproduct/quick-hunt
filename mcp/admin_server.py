"""
job-hunter-admin MCP server

Connects to Claude Desktop (or any MCP-compatible agent) via stdio.
Exposes the Job Hunter local stack as natural-language-callable tools.

Usage:
  python mcp/admin_server.py

Claude Desktop config (~/.../claude_desktop_config.json):
  See mcp/claude_desktop_config_snippet.json

Environment variables (all optional, have defaults for local dev):
  JH_API_URL        — FastAPI base URL (default: http://localhost:8001)
  JH_ADMIN_API_KEY  — X-API-Key value from infra/.env
  JH_REDIS_URL      — Redis URL (default: redis://localhost:6379/0)
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP
from tools import (
    health, logs, queues, cron, features, docker_tools, actions,
    database, redis_tools, system, pipeline,
    jobs, candidates, analytics, blacklist, scripts, kubectl_tools,
)

mcp = FastMCP(
    "job-hunter-admin",
    instructions=(
        "You are connected to the Job Hunter production stack. "
        "Use these tools to monitor system health, inspect logs, manage Celery workers, "
        "track cron job history, toggle feature flags, control Docker containers, "
        "trigger maintenance actions and cron tasks on demand, "
        "prefer operator workflows for risky work: preview the action, summarize impact, "
        "ask for explicit confirmation, run it, wait for the task, then summarize results, "
        "monitor database and Redis health, track job pipeline progress, "
        "view system resources, manage job records (search/update/delete), "
        "manage candidate profiles, browse email send logs and funnel analytics, "
        "manage the company blacklist, "
        "and control the Kubernetes cluster via kubectl_tools: get pod/cluster status, "
        "tail worker logs (including previous crashed containers), get all pod logs at once, "
        "view KEDA ScaledObject state, describe KEDA scalers, restart/scale deployments, "
        "force-delete stuck pods, pause/resume KEDA scaling, get RabbitMQ queue depths, "
        "and manage port-forwards (start_port_forwards/stop_port_forwards/get_port_forward_status) "
        "so cluster services are reachable at localhost:8002 (api), :3001 (dashboard), "
        ":15673 (rabbitmq), :5433 (postgres), :6380 (redis), :11435 (ollama). "
        "All operations target localhost or the configured Kubernetes namespace."
    ),
)

health.register(mcp)
logs.register(mcp)
queues.register(mcp)
cron.register(mcp)
features.register(mcp)
docker_tools.register(mcp)
actions.register(mcp)
database.register(mcp)
redis_tools.register(mcp)
system.register(mcp)
pipeline.register(mcp)
jobs.register(mcp)
candidates.register(mcp)
analytics.register(mcp)
blacklist.register(mcp)
scripts.register(mcp)
kubectl_tools.register(mcp)

if __name__ == "__main__":
    mcp.run(transport="stdio")
