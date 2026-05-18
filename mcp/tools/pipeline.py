from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_job_pipeline_status() -> str:
        """
        Show job counts broken down by status, representing the full
        application pipeline: new -> scored -> cover_generated -> hr_found ->
        sent / bounced / ignored / error / filtered. Includes total active
        jobs and percentage at each stage.
        """
        data = await api("GET", "/admin/pipeline/status", cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_processing_speed() -> str:
        """
        Show processing throughput metrics: jobs scraped/min, cover letters
        generated/min, emails sent/min, and HR emails discovered/min over
        the last hour. Helps identify bottlenecks in the pipeline.
        """
        data = await api("GET", "/admin/pipeline/speed", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_failure_trends() -> str:
        """
        Show failure analysis: failed tasks per hour over the last 24 hours,
        top error categories, most frequently failing task names, and
        recent error messages.
        """
        data = await api("GET", "/admin/pipeline/failures", cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_worker_throughput() -> str:
        """
        Show per-worker throughput: tasks completed and failed per worker
        service over the last hour, average task duration, and current
        queue drain rate.
        """
        data = await api("GET", "/admin/workers/throughput", cache_ttl=30)
        return fmt(data)
