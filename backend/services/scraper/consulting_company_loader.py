"""Runtime loader for the consulting scraper's company roster.

Mirrors mnc_company_loader: reads sentinel + per-tenant rows from
`consulting_companies`, with tenant rows shadowing sentinel by name.
"""
from __future__ import annotations

import structlog
from sqlalchemy import or_, select

from services.api.core.database import get_worker_session_factory
from services.api.models.db import ConsultingCompany, SENTINEL_TENANT_ID

logger = structlog.get_logger(__name__)


async def load_active_consulting_companies(tenant_id: str | None) -> list[dict]:
    """Return the active consulting/outsourcing company list for this tenant."""
    tid = tenant_id or SENTINEL_TENANT_ID
    sf = get_worker_session_factory()

    async with sf() as session:
        rows = (await session.execute(
            select(ConsultingCompany).where(
                or_(
                    ConsultingCompany.tenant_id == tid,
                    ConsultingCompany.tenant_id == SENTINEL_TENANT_ID,
                )
            )
        )).scalars().all()

    by_name: dict[str, ConsultingCompany] = {}
    for r in rows:
        key = (r.name or "").lower()
        existing = by_name.get(key)
        if existing is None:
            by_name[key] = r
            continue
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
        "consulting_companies_loaded",
        tenant_id=tid,
        total_rows=len(rows),
        merged=len(by_name),
        active=len(out),
    )
    return out
