"""Wellfound (formerly AngelList Talent) adapter — GraphQL SPA; requires auth.

wellfound.com is a React SPA that uses authenticated GraphQL queries.
Unauthenticated requests return an empty page or redirect to login.
Playwright is blocked by Cloudflare bot detection.
TODO: re-enable using an authenticated session token or official API access.
"""
from typing import Optional

import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class WellfoundAdapter(BaseAdapter):
    PORTAL_NAME = "wellfound"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.warning(
            "portal_unavailable",
            portal=self.PORTAL_NAME,
            reason="GraphQL SPA requiring auth; Playwright blocked by Cloudflare",
        )
        return []

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
