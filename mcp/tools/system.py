from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_system_resources() -> str:
        """
        Get CPU, memory, and disk usage metrics for each Docker container
        in the stack. Shows per-container resource limits and actual usage.
        """
        data = await api("GET", "/admin/system/resources", cache_ttl=10, timeout="long")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_service_uptime() -> str:
        """
        Show container start times and uptime for each service in the stack.
        Helps detect recently restarted or crash-looping services.
        """
        data = await api("GET", "/admin/system/uptime", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_environment_config() -> str:
        """
        Validate that all critical environment variables are set for the
        running services. Values are masked for security. Shows missing
        or empty config entries.
        """
        data = await api("GET", "/admin/system/env-check", cache_ttl=60)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_api_latency() -> str:
        """
        Show API response latency metrics: p50, p95, p99 response times
        from the Prometheus metrics endpoint. Helps identify performance
        degradation.
        """
        data = await api("GET", "/admin/system/latency", cache_ttl=10)
        return fmt(data)
