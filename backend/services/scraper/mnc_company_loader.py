"""Runtime loader for the MNC scraper's company roster.

The hardcoded list in `mnc_companies.py` is the *seed* data, not the
runtime source of truth. At dispatch time we load active rows from the
DB-backed `mnc_companies` table, merging sentinel + per-tenant rows
(tenant overrides shadow sentinel by name).
"""
from __future__ import annotations

import structlog
from sqlalchemy import or_, select

from services.api.core.database import get_worker_session_factory
from services.api.models.db import MncCompany, SENTINEL_TENANT_ID

logger = structlog.get_logger(__name__)


async def load_active_mnc_companies(tenant_id: str | None) -> list[dict]:
    """Return the active company list to scrape for this tenant.

    Behaviour:
      * Reads sentinel rows + the caller's tenant rows.
      * If a tenant row exists with the same (case-insensitive) name as a
        sentinel row, the tenant row wins (allowing per-tenant overrides
        or shadow-disable of global defaults).
      * Rows with active=False after the merge are filtered out.

    Returned dicts have the exact shape `MNCCareerAdapter._scrape_company`
    consumes: keys `name`, `career_url`, `ats`, `ats_slug`.
    """
    tid = tenant_id or SENTINEL_TENANT_ID
    sf = get_worker_session_factory()

    async with sf() as session:
        rows = (await session.execute(
            select(MncCompany).where(
                or_(
                    MncCompany.tenant_id == tid,
                    MncCompany.tenant_id == SENTINEL_TENANT_ID,
                )
            )
        )).scalars().all()

    # Build map keyed by lowercase name, tenant rows shadowing sentinel.
    by_name: dict[str, MncCompany] = {}
    for r in rows:
        key = (r.name or "").lower()
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = r
            continue
        # If both are present, prefer the non-sentinel (tenant) row.
        if existing.tenant_id == SENTINEL_TENANT_ID and r.tenant_id != SENTINEL_TENANT_ID:
            by_name[key] = r

    active = [r for r in by_name.values() if r.active]
    active.sort(key=lambda r: (r.name or "").lower())

    out = [
        {
            "name": r.name,
            "career_url": r.career_url,
            "ats": r.ats or "custom",
            "ats_slug": r.ats_slug or "",
        }
        for r in active
    ]
    logger.info(
        "mnc_companies_loaded",
        tenant_id=tid,
        total_rows=len(rows),
        merged=len(by_name),
        active=len(out),
    )
    return out
