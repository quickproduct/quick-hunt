"""MCP tools for email analytics — send log browsing, funnel stats, delivery reports."""
from mcp.server.fastmcp import FastMCP
from ._http import api, fmt
from ._base import track_duration, clamp

_VALID_SEND_STATUSES = {
    "queued", "sent", "deferred", "soft_bounced", "blocked",
    "delivered", "opened", "clicked", "bounced", "spam",
    "unsubscribed", "error",
}


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @track_duration
    async def get_send_logs(
        candidate_id: str = "",
        status: str = "",
        sent_after: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> str:
        """
        Browse email send logs with job title and company details attached.

        candidate_id: filter by candidate UUID
        status:       filter by delivery status —
                      queued | sent | deferred | soft_bounced | blocked |
                      delivered | opened | clicked | bounced | spam | unsubscribed | error
        sent_after:   ISO date string, e.g. "2024-01-01" — only show logs from this date
        limit:        rows to return (1–500, default 50)
        offset:       pagination offset
        """
        params: dict = {
            "limit": clamp(limit, 1, 500),
            "offset": max(0, offset),
        }
        if candidate_id.strip():
            params["candidate_id"] = candidate_id.strip()
        if status.strip():
            params["status"] = status.strip()
        if sent_after.strip():
            params["sent_after"] = sent_after.strip()

        data = await api("GET", "/admin/send-logs", params=params, cache_ttl=15)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_funnel_stats(
        candidate_id: str = "",
        days: int = 30,
    ) -> str:
        """
        Email delivery funnel stats for the last N days.

        Returns per-status counts and computed rates:
          delivery_rate  = delivered / sent
          open_rate      = opened / delivered
          click_rate     = clicked / opened
          bounce_rate    = bounced / sent

        candidate_id: filter by candidate UUID (leave empty for all candidates)
        days:         look-back window in days (1–365, default 30)
        """
        params: dict = {"days": clamp(days, 1, 365)}
        if candidate_id.strip():
            params["candidate_id"] = candidate_id.strip()

        data = await api("GET", "/admin/send-logs/funnel", params=params, cache_ttl=30)
        return fmt(data)

    @mcp.tool()
    @track_duration
    async def get_email_delivery_report(days: int = 14) -> str:
        """
        Daily email delivery breakdown by provider and status for the last N days.
        Useful for spotting delivery degradations, provider outages, or sudden
        bounce spikes across time.

        days: look-back window in days (1–90, default 14)
        """
        data = await api(
            "GET",
            "/admin/send-logs/delivery-report",
            params={"days": clamp(days, 1, 90)},
            cache_ttl=60,
        )
        return fmt(data)
