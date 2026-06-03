"""MNC company list CRUD router — source of truth for MNC scraping.

Mirrors the blacklist pattern: tenant-scoped rows plus a SENTINEL_TENANT_ID
seed set seen by every tenant. Tenant rows shadow sentinel rows by name —
the scraper loader treats a tenant row with active=False as an explicit
removal of the corresponding global default.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import MncCompany, SENTINEL_TENANT_ID, User
from services.api.schemas.schemas import (
    MncCompanyCreate,
    MncCompanyOut,
    MncCompanyUpdate,
)

router = APIRouter(prefix="/mnc-companies", tags=["mnc-companies"])
Auth = Annotated[User, Depends(get_current_user)]

_ATS_REQUIRES_SLUG = {"greenhouse", "lever", "smartrecruiters"}


def _to_out(row: MncCompany) -> dict:
    """Build the response dict, computing the synthetic `is_global` flag."""
    return {
        "id": row.id,
        "name": row.name,
        "career_url": row.career_url,
        "ats": row.ats,
        "ats_slug": row.ats_slug,
        "active": row.active,
        "is_global": row.tenant_id == SENTINEL_TENANT_ID,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


@router.get("", response_model=list[MncCompanyOut])
async def list_mnc_companies(current_user: Auth, db: AsyncSession = Depends(get_db)):
    """Return sentinel + tenant rows merged.

    Tenant rows shadow sentinel rows by name (case-insensitive). A tenant
    row with active=False therefore visibly disables a global default.
    """
    result = await db.execute(
        select(MncCompany)
        .where(
            or_(
                MncCompany.tenant_id == current_user.tenant_id,
                MncCompany.tenant_id == SENTINEL_TENANT_ID,
            )
        )
        .order_by(MncCompany.name)
    )
    rows = result.scalars().all()

    # Build by-name map, tenant rows winning over sentinel.
    by_name: dict[str, MncCompany] = {}
    for r in rows:
        key = (r.name or "").lower()
        existing = by_name.get(key)
        if existing is None or (
            existing.tenant_id == SENTINEL_TENANT_ID and r.tenant_id == current_user.tenant_id
        ):
            by_name[key] = r

    merged = sorted(by_name.values(), key=lambda r: (r.name or "").lower())
    return [_to_out(r) for r in merged]


@router.post("", response_model=MncCompanyOut, status_code=status.HTTP_201_CREATED)
async def add_mnc_company(
    body: MncCompanyCreate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    # Reject duplicate name within this tenant (case-insensitive).
    existing = await db.execute(
        select(MncCompany).where(
            MncCompany.tenant_id == current_user.tenant_id,
            MncCompany.name.ilike(body.name),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{body.name}' is already in your MNC list",
        )

    entry = MncCompany(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=body.name.strip(),
        career_url=body.career_url.strip(),
        ats=body.ats,
        ats_slug=(body.ats_slug or None),
        active=body.active,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return _to_out(entry)


@router.put("/{entry_id}", response_model=MncCompanyOut)
async def update_mnc_company(
    entry_id: str,
    body: MncCompanyUpdate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(MncCompany, entry_id)
    if not entry or entry.tenant_id != current_user.tenant_id:
        # Sentinel rows are read-only; force users to add a tenant row to override.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found or read-only (global defaults cannot be edited)",
        )

    if body.name is not None:
        entry.name = body.name.strip()
    if body.career_url is not None:
        entry.career_url = body.career_url.strip()
    if body.ats is not None:
        entry.ats = body.ats
    if body.ats_slug is not None:
        entry.ats_slug = body.ats_slug.strip() or None
    if body.active is not None:
        entry.active = body.active

    # Slug-required check uses the resulting row, not just the patch body.
    if entry.ats in _ATS_REQUIRES_SLUG and not (entry.ats_slug and entry.ats_slug.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ats_slug is required when ats is '{entry.ats}'",
        )

    await db.flush()
    await db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mnc_company(
    entry_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(MncCompany, entry_id)
    if not entry or entry.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found or read-only (use /disable for global defaults)",
        )
    await db.delete(entry)


@router.post("/{entry_id}/disable", response_model=MncCompanyOut, status_code=status.HTTP_201_CREATED)
async def disable_mnc_company(
    entry_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    """For sentinel (global) rows: create a shadowing tenant row with active=False.

    This is the UI "remove" path for global defaults — the original sentinel
    row stays untouched (other tenants still see it) but the loader for *this*
    tenant will skip it because the same-name tenant row wins and is inactive.
    """
    entry = await db.get(MncCompany, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.tenant_id == current_user.tenant_id:
        # Already tenant-owned — just flip active=False.
        entry.active = False
        await db.flush()
        await db.refresh(entry)
        return _to_out(entry)

    if entry.tenant_id != SENTINEL_TENANT_ID:
        raise HTTPException(status_code=404, detail="Entry not found")

    # Check whether a shadowing tenant row already exists.
    shadow = (await db.execute(
        select(MncCompany).where(
            MncCompany.tenant_id == current_user.tenant_id,
            MncCompany.name.ilike(entry.name),
        )
    )).scalar_one_or_none()

    if shadow is not None:
        shadow.active = False
        await db.flush()
        await db.refresh(shadow)
        return _to_out(shadow)

    shadow = MncCompany(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=entry.name,
        career_url=entry.career_url,
        ats=entry.ats,
        ats_slug=entry.ats_slug,
        active=False,
    )
    db.add(shadow)
    await db.flush()
    await db.refresh(shadow)
    return _to_out(shadow)
