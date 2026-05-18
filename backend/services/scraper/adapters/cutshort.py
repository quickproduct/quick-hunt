"""Cutshort adapter — React SPA; /api/jobs returns 404.

cutshort.io is a React SPA.  The /api/jobs endpoint returns 404.
Job listings are loaded via authenticated GraphQL calls requiring a
logged-in session.  Playwright is blocked by bot detection.
TODO: re-enable if an unauthenticated API endpoint becomes available.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class CutshortAdapter(BaseAdapter):
    PORTAL_NAME = "cutshort"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="React SPA; /api/jobs returns 404, GraphQL requires auth",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
