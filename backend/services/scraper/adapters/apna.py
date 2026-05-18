"""Apna adapter — React SPA with no accessible public API.

apna.co renders job listings entirely client-side.  Plain HTTP requests
return a JS bundle shell with no job data.  Playwright is blocked by
bot detection on the job search pages.
TODO: re-enable when the mobile app API endpoints are mapped.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class ApnaAdapter(BaseAdapter):
    PORTAL_NAME = "apna"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="React SPA; job listings loaded client-side, Playwright blocked by bot detection",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
