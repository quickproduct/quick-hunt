"""Instahyre adapter — Next.js SPA; /api/v1/opportunity/ returns 404.

instahyre.com uses Next.js with client-side data fetching.  The v1 REST
API endpoint returns 404.  Playwright is blocked by bot detection.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class InstahyreAdapter(BaseAdapter):
    PORTAL_NAME = "instahyre"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="Next.js SPA; REST API returns 404, Playwright blocked by bot detection",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
