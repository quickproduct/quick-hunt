"""Remotive adapter — currently blocked by Cloudflare (HTTP 526).

The remotive.io API and RSS feed both return 403/526 from the server's IP.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when a proxy or alternative API endpoint is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class RemotiveAdapter(BaseAdapter):
    PORTAL_NAME = "remotive"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="Cloudflare blocks requests from this IP; skipping to avoid 30-min timeout",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
