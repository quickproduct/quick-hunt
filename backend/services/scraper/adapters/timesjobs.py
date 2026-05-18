"""TimesJobs adapter — Next.js SPA; httpx gets a 12KB JS shell with no job data.

The site migrated to Next.js client-side rendering.  Plain HTTP returns the
skeleton app bundle; actual job results are fetched client-side.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class TimesJobsAdapter(BaseAdapter):
    PORTAL_NAME = "timesjobs"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="Next.js SPA; httpx returns 12KB JS shell with no job listings",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
