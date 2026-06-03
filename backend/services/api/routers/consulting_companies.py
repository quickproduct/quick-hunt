"""Consulting/outsourcing company list CRUD router — source of truth for consulting scraping.

Same sentinel + tenant-shadow pattern as the MNC router.
"""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import ConsultingCompany, SENTINEL_TENANT_ID, User
from services.api.schemas.schemas import (
    ConsultingCompanyCreate,
    ConsultingCompanyOut,
    ConsultingCompanyUpdate,
)

router = APIRouter(prefix="/consulting-companies", tags=["consulting-companies"])
Auth = Annotated[User, Depends(get_current_user)]

_ATS_REQUIRES_SLUG = {"greenhouse", "lever", "smartrecruiters"}


def _to_out(row: ConsultingCompany) -> dict:
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


@router.get("", response_model=list[ConsultingCompanyOut])
async def list_consulting_companies(current_user: Auth, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ConsultingCompany)
        .where(
            or_(
                ConsultingCompany.tenant_id == current_user.tenant_id,
                ConsultingCompany.tenant_id == SENTINEL_TENANT_ID,
            )
        )
        .order_by(ConsultingCompany.name)
    )
    rows = result.scalars().all()

    by_name: dict[str, ConsultingCompany] = {}
    for r in rows:
        key = (r.name or "").lower()
        existing = by_name.get(key)
        if existing is None or (
            existing.tenant_id == SENTINEL_TENANT_ID and r.tenant_id == current_user.tenant_id
        ):
            by_name[key] = r

    merged = sorted(by_name.values(), key=lambda r: (r.name or "").lower())
    return [_to_out(r) for r in merged]


@router.post("", response_model=ConsultingCompanyOut, status_code=status.HTTP_201_CREATED)
async def add_consulting_company(
    body: ConsultingCompanyCreate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(
        select(ConsultingCompany).where(
            ConsultingCompany.tenant_id == current_user.tenant_id,
            ConsultingCompany.name.ilike(body.name),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{body.name}' is already in your consulting list",
        )

    entry = ConsultingCompany(
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


@router.put("/{entry_id}", response_model=ConsultingCompanyOut)
async def update_consulting_company(
    entry_id: str,
    body: ConsultingCompanyUpdate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(ConsultingCompany, entry_id)
    if not entry or entry.tenant_id != current_user.tenant_id:
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

    if entry.ats in _ATS_REQUIRES_SLUG and not (entry.ats_slug and entry.ats_slug.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"ats_slug is required when ats is '{entry.ats}'",
        )

    await db.flush()
    await db.refresh(entry)
    return _to_out(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_consulting_company(
    entry_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(ConsultingCompany, entry_id)
    if not entry or entry.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entry not found or read-only (use /disable for global defaults)",
        )
    await db.delete(entry)


@router.post("/{entry_id}/disable", response_model=ConsultingCompanyOut, status_code=status.HTTP_201_CREATED)
async def disable_consulting_company(
    entry_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(ConsultingCompany, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")

    if entry.tenant_id == current_user.tenant_id:
        entry.active = False
        await db.flush()
        await db.refresh(entry)
        return _to_out(entry)

    if entry.tenant_id != SENTINEL_TENANT_ID:
        raise HTTPException(status_code=404, detail="Entry not found")

    shadow = (await db.execute(
        select(ConsultingCompany).where(
            ConsultingCompany.tenant_id == current_user.tenant_id,
            ConsultingCompany.name.ilike(entry.name),
        )
    )).scalar_one_or_none()

    if shadow is not None:
        shadow.active = False
        await db.flush()
        await db.refresh(shadow)
        return _to_out(shadow)

    shadow = ConsultingCompany(
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
