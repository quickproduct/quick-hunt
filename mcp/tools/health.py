from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, tool_error


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_system_health() -> str:
        """
        Check connectivity status of all core services: PostgreSQL, Redis,
        RabbitMQ, and Ollama. Returns 'ok' or 'error' per service with
        response latency for each.
        """
        data = await api("GET", "/admin/system/health", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_quota_status() -> str:
        """
        Show current API quota usage: Groq RPM (requests per minute) consumed
        vs limit, and HR email provider daily quota (Hunter.io, Snov.io).
        Useful for diagnosing slowdowns in cover letter generation or email discovery.
        """
        data = await api("GET", "/admin/quota", cache_ttl=10)
        return fmt(data)
