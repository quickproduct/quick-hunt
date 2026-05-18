"""IIMJobs adapter — JS-rendered; LD+JSON on page contains no job listings.

IIMJobs (a Naukri/Info Edge subsidiary) renders job results client-side.
The HTML response has a BreadcrumbList and an empty ItemList in LD+JSON
but zero actual job entries.  Playwright is blocked by bot detection.
TODO: re-enable using Naukri's API with iimjobs-specific parameters once
the API contract is understood.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class IIMJobsAdapter(BaseAdapter):
    PORTAL_NAME = "iimjobs"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="JS-rendered; LD+JSON is empty, Playwright blocked by bot detection",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
