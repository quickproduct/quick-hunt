"""Tenant repository — DB queries for the tenants table."""

import re
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.models.db import Tenant, UsageLog


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:80]


async def get_tenant_by_id(session: AsyncSession, tenant_id: str) -> Optional[Tenant]:
    return await session.get(Tenant, tenant_id)


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Optional[Tenant]:
    result = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return result.scalar_one_or_none()


async def create_tenant(session: AsyncSession, name: str) -> Tenant:
    base_slug = _slugify(name)
    slug = base_slug
    # Ensure slug uniqueness by appending a short UUID segment if needed
    existing = await get_tenant_by_slug(session, slug)
    if existing:
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"
    tenant = Tenant(id=str(uuid.uuid4()), name=name, slug=slug)
    session.add(tenant)
    await session.flush()
    return tenant


async def get_usage_summary(
    session: AsyncSession, tenant_id: str
) -> dict:
    """Return counts of usage_logs grouped by action_type for this tenant."""
    result = await session.execute(
        select(UsageLog.action_type, func.count(UsageLog.id).label("count"))
        .where(UsageLog.tenant_id == tenant_id)
        .group_by(UsageLog.action_type)
    )
    return {row.action_type: row.count for row in result.all()}
