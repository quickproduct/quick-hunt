"""Blacklist utilities shared by scraper and sender Celery workers.

Workers have no HTTP request context, so these functions create their own
DB sessions and query the blacklisted_companies table directly.

Matching uses case-insensitive substring check in both directions so that
partial names work:
  - "WebMD" blacklisted  →  matches "WebMD Health Corp" (scraped company)
  - "FindLaw" blacklisted →  matches "FindLaw – a Thomson Reuters Business"
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def get_blacklisted_names(session: "AsyncSession") -> frozenset[str]:
    """Return all blacklisted company names as a lowercase frozenset.

    Queries across ALL tenants so Celery workers (which have no tenant
    context) still enforce the blacklist correctly.

    Call once per Celery task, not per-job, to minimise DB round-trips.
    """
    from sqlalchemy import select
    from services.api.models.db import BlacklistedCompany

    result = await session.execute(select(BlacklistedCompany.name))
    return frozenset(row[0].lower() for row in result.all())


def is_company_blacklisted(company_name: str, blacklist: frozenset[str]) -> bool:
    """Return True if company_name matches any entry in the blacklist.

    Uses bidirectional substring matching (case-insensitive) on two forms:
      1. Normal lowercase           — "WebMD Health Services" → "webmd health services"
      2. Spaces-stripped lowercase  — "ImpactGuru" and "Impact Guru" both → "impactguru"

    The second form catches cases where the scraped name omits spaces
    (e.g. "ImpactGuru") but the blacklist entry has them (e.g. "Impact Guru"),
    or vice-versa.
    """
    if not company_name or not blacklist:
        return False
    normalized = company_name.lower().strip()
    normalized_nospace = normalized.replace(" ", "")
    for bl in blacklist:
        bl_nospace = bl.replace(" ", "")
        if bl in normalized or normalized in bl:
            return True
        if bl_nospace in normalized_nospace or normalized_nospace in bl_nospace:
            return True
    return False
