"""Arc.dev adapter — React SPA with no accessible public API endpoint.

arc.dev is a React SPA; plain HTTP requests get an empty shell.
The /api/jobs endpoint returns 404. Playwright is blocked by bot detection.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class ArcDevAdapter(BaseAdapter):
    PORTAL_NAME = "arcdev"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="React SPA with no public API; Playwright blocked by bot detection",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
