"""Blacklisted companies CRUD router."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import BlacklistedCompany, User
from services.api.schemas.schemas import (
    BlacklistedCompanyCreate,
    BlacklistedCompanyOut,
    BlacklistedCompanyUpdate,
)

router = APIRouter(prefix="/blacklist", tags=["blacklist"])
Auth = Annotated[User, Depends(get_current_user)]

# Sentinel tenant holds globally seeded entries visible to all tenants
SENTINEL_TENANT_ID = "00000000-0000-0000-0000-000000000001"


@router.get("", response_model=list[BlacklistedCompanyOut])
async def list_blacklist(current_user: Auth, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(BlacklistedCompany)
        .where(
            or_(
                BlacklistedCompany.tenant_id == current_user.tenant_id,
                BlacklistedCompany.tenant_id == SENTINEL_TENANT_ID,
            )
        )
        .order_by(BlacklistedCompany.name)
    )
    return result.scalars().all()


@router.post("", response_model=BlacklistedCompanyOut, status_code=status.HTTP_201_CREATED)
async def add_to_blacklist(
    body: BlacklistedCompanyCreate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    # Check for duplicate name within this tenant (case-insensitive)
    existing = await db.execute(
        select(BlacklistedCompany).where(
            BlacklistedCompany.tenant_id == current_user.tenant_id,
            BlacklistedCompany.name.ilike(body.name),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{body.name}' is already blacklisted",
        )

    entry = BlacklistedCompany(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        name=body.name.strip(),
        reason=body.reason,
    )
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return entry


@router.put("/{entry_id}", response_model=BlacklistedCompanyOut)
async def update_blacklist_entry(
    entry_id: str,
    body: BlacklistedCompanyUpdate,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(BlacklistedCompany, entry_id)
    if not entry or entry.tenant_id not in (current_user.tenant_id, SENTINEL_TENANT_ID):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    entry.reason = body.reason
    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_blacklist(
    entry_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    entry = await db.get(BlacklistedCompany, entry_id)
    if not entry or entry.tenant_id not in (current_user.tenant_id, SENTINEL_TENANT_ID):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")
    await db.delete(entry)
