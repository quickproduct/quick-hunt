"""Remote.co adapter — WP REST API times out; JS-rendered site blocks httpx.

The WP JSON API at remote.co/wp-json/wp/v2/job-listings consistently times out.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when the API becomes accessible or a proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class RemoteCoAdapter(BaseAdapter):
    PORTAL_NAME = "remoteco"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="WP REST API times out from this IP; skipping to avoid 30-min timeout",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
