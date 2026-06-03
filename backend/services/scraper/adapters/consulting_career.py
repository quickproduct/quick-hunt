"""Consulting / IT outsourcing direct career-page scraper.

The ATS-routing logic is identical to the MNC adapter — only the
`source_portal` tag on each emitted `RawJob` differs (so consulting
results sit in the same `jobs` table but can be filtered separately).

This wraps `MNCCareerAdapter` rather than duplicating ~600 lines: we
run its 8-tier scrape, then rewrite `source_portal` on every result.
"""
from __future__ import annotations

from typing import Optional

import structlog

from services.scraper.adapters.mnc_career import MNCCareerAdapter
from services.scraper.base_adapter import JobQuery, RawJob
from services.scraper.consulting_companies import CONSULTING_COMPANIES

logger = structlog.get_logger(__name__)

PORTAL_NAME = "consulting_direct"


class ConsultingCareerAdapter(MNCCareerAdapter):
    """Scrapes software-engineer roles from curated consulting / outsourcing firms.

    Inherits the full 8-tier ATS routing (greenhouse/lever/smartrecruiters/
    workday/icims/taleo/bamboohr/custom) from MNCCareerAdapter. Overrides
    the portal tag so results are distinguishable in the `jobs` table.

    NOTE: The parent's per-tier methods construct `RawJob(source_portal=PORTAL_NAME)`
    using the *module-level* constant in `mnc_career.py`, not `self.PORTAL_NAME`.
    To guarantee correct tagging regardless of which code path produces the
    RawJob (search_jobs vs. _scrape_company called directly by a Celery task),
    we wrap *every* public entry point and retag the results here.
    """

    PORTAL_NAME = PORTAL_NAME

    def _retag(self, jobs: list[RawJob]) -> list[RawJob]:
        for j in jobs:
            j.source_portal = PORTAL_NAME
        return jobs

    async def search_jobs(
        self,
        query: JobQuery,
        companies: list[dict] | None = None,
    ) -> list[RawJob]:
        if companies is None:
            companies = CONSULTING_COMPANIES
        results = await super().search_jobs(query, companies=companies)
        return self._retag(results)

    async def _scrape_company(self, client, company) -> list[RawJob]:
        # Per-company Celery task calls this directly. Retag here so the
        # task wrapper isn't the only thing standing between us and a
        # silently mis-tagged row in the `jobs` table.
        return self._retag(await super()._scrape_company(client, company))

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
