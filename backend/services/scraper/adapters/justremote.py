"""JustRemote adapter — JS-rendered site (styled-components); httpx gets no job listings.

justremote.co uses styled-components with hashed class names; the search results
are rendered client-side. Plain httpx returns the skeleton with 0 jobs.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class JustRemoteAdapter(BaseAdapter):
    PORTAL_NAME = "justremote"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="JS-rendered styled-components app; httpx returns 0 job listings",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
