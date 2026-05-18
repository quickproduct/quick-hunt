"""Foundit (formerly Monster India) adapter — React SPA; no accessible JSON API.

The site is a React SPA.  The search results page returns 251KB HTML but all
job listings are rendered client-side via XHR.  No public or internal JSON
API endpoint was found during probe (all returned 404 or empty responses).
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class FounditAdapter(BaseAdapter):
    PORTAL_NAME = "foundit"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="React SPA; job listings loaded client-side, no public API available",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
