"""Billing service — Razorpay plan management and webhook handling."""

import hashlib
import hmac
import uuid

import structlog
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.config import get_settings
from services.api.models.db import BillingSubscription, Tenant

logger = structlog.get_logger(__name__)

# ── Plan definitions ──────────────────────────────────────────────────────────

PLANS: dict[str, dict] = {
    "free": {
        "applications_per_day": 5,
        "ai_credits_per_month": 50,
        "active_automations": 1,
        "price_inr": 0,
        "label": "Free",
    },
    "pro": {
        "applications_per_day": 50,
        "ai_credits_per_month": 500,
        "active_automations": 5,
        "price_inr": 999,
        "label": "Pro",
    },
    "premium": {
        "applications_per_day": -1,  # unlimited
        "ai_credits_per_month": -1,
        "active_automations": -1,
        "price_inr": 2999,
        "label": "Premium",
    },
}


def list_plans() -> list[dict]:
    return [{"id": k, **v} for k, v in PLANS.items()]


async def get_subscription(
    session: AsyncSession, tenant_id: str
) -> BillingSubscription | None:
    from sqlalchemy import select
    result = await session.execute(
        select(BillingSubscription)
        .where(BillingSubscription.tenant_id == tenant_id)
        .order_by(BillingSubscription.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def create_checkout(
    session: AsyncSession,
    tenant: Tenant,
    plan: str,
) -> dict:
    """Create a Razorpay payment link for the given plan."""
    if plan not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown plan: {plan}. Valid: {list(PLANS.keys())}",
        )
    plan_data = PLANS[plan]
    if plan_data["price_inr"] == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Free plan does not require checkout.",
        )

    settings = get_settings()
    if not settings.razorpay_key_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured.",
        )

    try:
        import razorpay
        client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
        payment_link = client.payment_link.create({
            "amount": plan_data["price_inr"] * 100,  # paise
            "currency": "INR",
            "description": f"AI Job Hunter — {plan_data['label']} Plan",
            "customer": {"email": tenant.slug + "@jobhunter.app"},
            "notify": {"sms": False, "email": True},
            "reminder_enable": False,
            "notes": {"tenant_id": tenant.id, "plan": plan},
            "callback_url": settings.frontend_url + "/billing/success",
            "callback_method": "get",
        })
        logger.info("checkout_created", tenant_id=tenant.id, plan=plan)
        return {"payment_link_url": payment_link["short_url"], "plan": plan}
    except Exception as exc:
        logger.error("checkout_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Payment gateway error.",
        )


async def handle_webhook(session: AsyncSession, payload: bytes, signature: str) -> dict:
    """Verify Razorpay webhook signature and update tenant plan."""
    settings = get_settings()

    # Verify HMAC-SHA256 signature
    expected = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid webhook signature."
        )

    import json
    event = json.loads(payload)
    event_type = event.get("event")

    if event_type == "payment_link.paid":
        notes = event.get("payload", {}).get("payment_link", {}).get("entity", {}).get("notes", {})
        tenant_id = notes.get("tenant_id")
        plan = notes.get("plan")
        if tenant_id and plan:
            await _activate_plan(session, tenant_id, plan, event)

    return {"received": True}


async def cancel_subscription(session: AsyncSession, tenant_id: str) -> None:
    sub = await get_subscription(session, tenant_id)
    if sub:
        sub.status = "cancelled"

    tenant = await session.get(Tenant, tenant_id)
    if tenant:
        tenant.plan = "free"

    await session.commit()
    logger.info("subscription_cancelled", tenant_id=tenant_id)


# ── Internal helpers ──────────────────────────────────────────────────────────

async def verify_callback(
    session: AsyncSession,
    tenant: Tenant,
    params: dict,
) -> dict:
    """Verify Razorpay payment-link callback signature and activate the plan."""
    settings = get_settings()

    # Razorpay callback signature: HMAC-SHA256(key=key_secret,
    #   msg="{payment_link_id}|{reference_id}|{status}|{payment_id}")
    msg = (
        f"{params['razorpay_payment_link_id']}"
        f"|{params['razorpay_payment_link_reference_id']}"
        f"|{params['razorpay_payment_link_status']}"
        f"|{params['razorpay_payment_id']}"
    )
    expected = hmac.new(
        settings.razorpay_key_secret.encode(),
        msg.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, params["razorpay_signature"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid payment signature.",
        )

    if params["razorpay_payment_link_status"] != "paid":
        return {"activated": False}

    # Fetch payment link from Razorpay to get notes (tenant_id, plan)
    try:
        import razorpay
        client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
        plink = client.payment_link.fetch(params["razorpay_payment_link_id"])
    except Exception as exc:
        logger.error("razorpay_fetch_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not verify payment with gateway.",
        )

    notes = plink.get("notes", {})
    plink_tenant_id = notes.get("tenant_id")
    plan = notes.get("plan")

    if plink_tenant_id != tenant.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Payment link does not belong to this account.",
        )
    if plan not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown plan in payment record.",
        )

    event_stub = {
        "payload": {"payment": {"entity": {"id": params["razorpay_payment_id"]}}}
    }
    await _activate_plan(session, tenant.id, plan, event_stub)
    logger.info("callback_verified", tenant_id=tenant.id, plan=plan)
    return {"activated": True, "plan": plan}


async def _activate_plan(
    session: AsyncSession, tenant_id: str, plan: str, event: dict
) -> None:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select

    tenant = await session.get(Tenant, tenant_id)
    if not tenant:
        return

    payment_id = event.get("payload", {}).get("payment", {}).get("entity", {}).get("id")

    # Idempotency: skip if subscription for this payment already exists
    if payment_id:
        existing = await session.execute(
            select(BillingSubscription).where(
                BillingSubscription.provider_sub_id == payment_id
            )
        )
        if existing.scalar_one_or_none():
            logger.info("plan_already_activated", tenant_id=tenant_id, payment_id=payment_id)
            return

    tenant.plan = plan
    sub = BillingSubscription(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        plan=plan,
        status="active",
        provider="razorpay",
        provider_sub_id=payment_id,
        current_period_end=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=30),
    )
    session.add(sub)
    await session.commit()
    logger.info("plan_activated", tenant_id=tenant_id, plan=plan)
