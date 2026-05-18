"""Tenant management endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import CurrentTenant, CurrentUser
from services.api.repositories import tenant_repo
from services.api.schemas.auth_schemas import TenantResponse, UpdateTenantRequest

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/me", response_model=TenantResponse)
async def get_my_tenant(tenant: CurrentTenant):
    return tenant


@router.put("/me", response_model=TenantResponse)
async def update_my_tenant(
    body: UpdateTenantRequest,
    tenant: CurrentTenant,
    db: AsyncSession = Depends(get_db),
):
    if body.name is not None:
        tenant.name = body.name
    if body.requires_approval is not None:
        tenant.requires_approval = body.requires_approval
    if body.auto_send is not None:
        tenant.auto_send = body.auto_send
    if body.score_threshold is not None:
        tenant.score_threshold = body.score_threshold
    await db.commit()
    return tenant


@router.get("/me/usage")
async def get_usage_summary(
    tenant: CurrentTenant,
    db: AsyncSession = Depends(get_db),
):
    summary = await tenant_repo.get_usage_summary(db, tenant.id)
    return {"tenant_id": tenant.id, "plan": tenant.plan, "usage": summary}
