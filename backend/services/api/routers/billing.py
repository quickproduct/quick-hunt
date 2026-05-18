"""Billing endpoints — plan listing, Razorpay checkout, webhook, cancel."""

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import CurrentTenant, OwnerOnly
from services.api.models.db import User
from services.api.services import billing_service

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/plans")
async def list_plans():
    return billing_service.list_plans()


@router.get("/subscription")
async def get_subscription(
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    sub = await billing_service.get_subscription(db, tenant.id)
    if not sub:
        return {"tenant_id": tenant.id, "plan": tenant.plan, "subscription": None}
    return {
        "tenant_id": tenant.id,
        "plan": tenant.plan,
        "subscription": {
            "id": sub.id,
            "status": sub.status,
            "provider": sub.provider,
            "current_period_end": sub.current_period_end,
        },
    }


@router.post("/create-checkout")
async def create_checkout(
    plan: str,
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    return await billing_service.create_checkout(db, tenant, plan)


@router.post("/webhook", status_code=200)
async def razorpay_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_razorpay_signature: str = Header(None, alias="X-Razorpay-Signature"),
):
    """Razorpay webhook — no auth, signature verified inside service."""
    body = await request.body()
    return await billing_service.handle_webhook(db, body, x_razorpay_signature or "")


@router.post("/cancel", status_code=204)
async def cancel_subscription(
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    await billing_service.cancel_subscription(db, tenant.id)


class CallbackParams(BaseModel):
    razorpay_payment_id: str
    razorpay_payment_link_id: str
    razorpay_payment_link_reference_id: str
    razorpay_payment_link_status: str
    razorpay_signature: str


@router.post("/verify-callback")
async def verify_callback(
    params: CallbackParams,
    tenant: CurrentTenant,
    _: User = Depends(OwnerOnly),
    db: AsyncSession = Depends(get_db),
):
    """Verify Razorpay payment-link callback and activate the plan immediately."""
    return await billing_service.verify_callback(db, tenant, params.model_dump())
