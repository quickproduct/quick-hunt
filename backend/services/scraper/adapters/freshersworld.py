"""Freshersworld adapter — returns 404 on all search URL patterns.

All search URL patterns tried (slug-based, query-string) return HTTP 404.
The site appears to have changed its URL structure or is blocking the requests.
TODO: re-enable when the correct URL pattern or an API endpoint is found.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class FreshersworldAdapter(BaseAdapter):
    PORTAL_NAME = "freshersworld"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="All search URL patterns return 404; site structure changed",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
