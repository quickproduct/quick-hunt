"""MCP tools for company blacklist management — list, add, remove."""
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt, _cache_invalidate
from ._base import track_duration


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def list_blacklist() -> str:
        """
        List all blacklisted companies. Jobs from these companies are excluded
        from all queries and the dashboard stats.

        Returns company name, reason (if set), and the entry ID needed for removal.
        """
        data = await api("GET", "/blacklist", cache_ttl=60)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def add_to_blacklist(company_name: str, reason: str = "") -> str:
        """
        Add a company to the blacklist so its jobs are excluded from the pipeline.
        The match is a case-insensitive bidirectional substring check, so
        "TechCorp" also blocks "techcorp solutions" and "the techcorp group".

        company_name: company name to blacklist (required)
        reason:       optional note explaining why this company is blacklisted
        """
        if not company_name.strip():
            return '{"error": "company_name is required"}'

        body: dict = {"name": company_name.strip()}
        if reason.strip():
            body["reason"] = reason.strip()

        data = await api("POST", "/blacklist", json=body)
        _cache_invalidate(path="GET:/blacklist:")
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def remove_from_blacklist(entry_id: str) -> str:
        """
        Remove a company from the blacklist by its entry ID.
        Use list_blacklist() first to find the ID for the company you want to unblock.

        entry_id: UUID of the blacklist entry (from list_blacklist)
        """
        if not entry_id.strip():
            return '{"error": "entry_id is required — call list_blacklist() to find it"}'

        data = await api("DELETE", f"/blacklist/{entry_id.strip()}")
        _cache_invalidate(path="GET:/blacklist:")
        return fmt(data)
