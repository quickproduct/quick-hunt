"""Himalayas adapter — currently returns HTTP 403 for all endpoints.

Both himalayas.app/jobs and himalayas.app/jobs/api return 403 from the server IP.
This stub returns immediately so workers are not blocked for 30 minutes.
TODO: re-enable when an accessible API endpoint or proxy is available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class HimalayasAdapter(BaseAdapter):
    PORTAL_NAME = "himalayas"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="HTTP 403 from all known endpoints; skipping to avoid 30-min timeout",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
