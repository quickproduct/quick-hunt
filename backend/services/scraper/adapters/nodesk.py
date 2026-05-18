"""NoDesk adapter — JS-rendered site; httpx gets an empty content shell.

nodesk.co uses client-side rendering; plain HTTP returns a Tachyons CSS shell
with no job listings. Playwright is blocked by the site.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class NoDeskAdapter(BaseAdapter):
    PORTAL_NAME = "nodesk"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="JS-rendered; httpx returns empty shell with no job listings",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
