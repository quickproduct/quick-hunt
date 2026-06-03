"""Webhook receivers — Resend and Brevo transactional email events."""
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.config import get_settings
from services.api.core.database import get_db
from services.api.models.db import Job, SendLog

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = structlog.get_logger(__name__)


# Resend event type → (send_log status, timestamp field to set)
EVENT_MAP = {
    "email.sent": ("sent", None),
    "email.delivered": ("delivered", "delivered_at"),
    "email.opened": ("opened", "opened_at"),
    "email.clicked": ("clicked", "clicked_at"),
    "email.bounced": ("bounced", None),
    "email.complained": ("bounced", None),
    "email.delivery_delayed": (None, None),
}


def _verify_resend_signature(payload: bytes, svix_id: str, svix_timestamp: str, svix_signature: str, secret: str) -> bool:
    """Verify Resend webhook signature using svix (HMAC-SHA256).
    Docs: https://resend.com/docs/dashboard/webhooks/introduction
    """
    try:
        # svix signs: "{svix_id}.{svix_timestamp}.{body}"
        signed_content = f"{svix_id}.{svix_timestamp}.{payload.decode()}".encode()
        # secret is prefixed with "whsec_" and base64-encoded
        import base64
        raw_secret = base64.b64decode(secret.removeprefix("whsec_"))
        expected = hmac.new(raw_secret, signed_content, hashlib.sha256).digest()
        expected_b64 = base64.b64encode(expected).decode()
        # svix_signature may be a comma-separated list of "v1,<sig>"
        for sig_entry in svix_signature.split(" "):
            if sig_entry.startswith("v1,"):
                if hmac.compare_digest(sig_entry[3:], expected_b64):
                    return True
        return False
    except Exception:
        return False


@router.post("/resend", status_code=status.HTTP_204_NO_CONTENT)
async def resend_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    svix_id: str = Header(default=""),
    svix_timestamp: str = Header(default=""),
    svix_signature: str = Header(default=""),
):
    settings = get_settings()
    raw_body = await request.body()

    # Verify signature if secret is configured
    if settings.resend_webhook_secret and svix_signature:
        valid = _verify_resend_signature(
            raw_body,
            svix_id,
            svix_timestamp,
            svix_signature,
            settings.resend_webhook_secret,
        )
        if not valid:
            logger.warning("resend_webhook_invalid_signature")
            raise HTTPException(status_code=403, detail="Invalid webhook signature")

    try:
        event: dict = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    await _process_event(event, db)


async def _process_event(event: dict[str, Any], db: AsyncSession) -> None:
    event_type = event.get("type", "")
    data = event.get("data", {})
    message_id = data.get("email_id", "")

    if not message_id:
        return

    # Find send_log by provider_message_id
    result = await db.execute(
        select(SendLog).where(SendLog.provider_message_id == message_id)
    )
    log = result.scalar_one_or_none()
    if not log:
        logger.debug("webhook_event_no_log", event_type=event_type, message_id=message_id)
        return

    mapping = EVENT_MAP.get(event_type)
    if not mapping or mapping[0] is None:
        return

    new_status, timestamp_field = mapping
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    updates: dict[str, Any] = {
        "status": new_status,
        "response_webhook_payload": event,
    }
    if timestamp_field:
        updates[timestamp_field] = now
    if event_type == "email.bounced":
        updates["error_message"] = data.get("reason", "Bounced")

    await db.execute(update(SendLog).where(SendLog.id == log.id).values(**updates))

    # Update job status for bounce/complaint
    if event_type in ("email.bounced", "email.complained"):
        await db.execute(update(Job).where(Job.id == log.job_id).values(status="bounced"))

    await db.commit()
    logger.info("webhook_event_processed", event_type=event_type, log_id=log.id, new_status=new_status)


@router.post("/resend/test")
async def resend_webhook_test():
    """Health check endpoint for webhook URL verification."""
    return {"status": "ok", "message": "Resend webhook endpoint is reachable"}


# ── Brevo transactional webhook ────────────────────────────────────────────────
# Brevo event  →  (send_log status,  timestamp field,       job status or None)

# (send_log_status, ts_field, job_status)
# retry_after_hours is used by retry_failed_sends_task — stored in error_message prefix
_BREVO_EVENT_MAP: dict[str, tuple[str, str | None, str | None]] = {
    # ── Positive outcomes ──────────────────────────────────────────────────
    "delivered":      ("delivered",  "delivered_at", None),
    "opened":         ("opened",     "opened_at",    None),   # any open
    "first_opening":  ("opened",     "opened_at",    None),   # first open (same)
    "click":          ("clicked",    "clicked_at",   None),
    # ── Retry after 3 hours ───────────────────────────────────────────────
    # soft_bounce: recipient server temporarily rejected (mailbox full, etc.)
    "soft_bounce":    ("soft_bounced", None,          None),
    # blocked: spam complaints + repeated hard bounces — PERMANENT (same as hard_bounce)
    "blocked":        ("blocked",    None,            "bounced"),
    # hard_bounce / invalid: bad address — clear hr_email, backfill finds new one
    "hard_bounce":    ("bounced",    None,            "bounced"),
    "invalid_email":  ("bounced",    None,            "bounced"),
    # ── Retry after 1 hour ────────────────────────────────────────────────
    # deferred: temporarily rejected, will retry sooner
    "deferred":       ("deferred",   None,            None),
    # ── Permanent — no retry ──────────────────────────────────────────────
    "spam":           ("spam",       None,            "bounced"),
    "unsubscribed":   ("unsubscribed", None,          None),
    # Informational only
    "request":        (None,         None,            None),
}


@router.post("/brevo", status_code=status.HTTP_204_NO_CONTENT)
async def brevo_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    secret: str = Query(default=""),
):
    """Receive Brevo transactional email events and sync status to SendLog.

    Brevo posts one JSON object per event.  We match via the ``message-id``
    field (stored in SendLog.provider_message_id).

    URL security: pass BREVO_WEBHOOK_SECRET as a ``?secret=`` query param.
    Set the same value in Brevo's webhook URL so forged requests are rejected.
    """
    settings = get_settings()

    # Validate secret token when configured
    if settings.brevo_webhook_secret:
        if not secret or not hmac.compare_digest(secret, settings.brevo_webhook_secret):
            logger.warning("brevo_webhook_invalid_secret", remote=request.client)
            raise HTTPException(status_code=403, detail="Invalid webhook secret")

    raw_body = await request.body()
    try:
        payload: dict = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Brevo sends a single object per request
    await _process_brevo_event(payload, db)


async def _process_brevo_event(event: dict[str, Any], db: AsyncSession) -> None:
    event_type: str = event.get("event", "")
    # Brevo includes angle brackets in message-id: <xxx@smtp-relay.mailin.fr>
    message_id: str = event.get("message-id", "").strip()

    if not message_id:
        logger.debug("brevo_webhook_no_message_id", event_type=event_type)
        return

    result = await db.execute(
        select(SendLog).where(SendLog.provider_message_id == message_id)
    )
    log = result.scalar_one_or_none()

    if not log:
        logger.debug("brevo_webhook_no_log", event_type=event_type, message_id=message_id)
        return

    mapping = _BREVO_EVENT_MAP.get(event_type)
    if mapping is None:
        logger.debug("brevo_webhook_unknown_event", event_type=event_type)
        return

    new_status, ts_field, new_job_status = mapping
    if new_status is None:
        return  # informational event, nothing to update

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    updates: dict[str, Any] = {
        "status": new_status,
        "response_webhook_payload": event,
    }
    if ts_field:
        updates[ts_field] = now
    if new_status in ("bounced", "failed") and event.get("reason"):
        updates["error_message"] = event["reason"]

    await db.execute(update(SendLog).where(SendLog.id == log.id).values(**updates))

    if new_job_status:
        # Permanent bounce — clear hr_email so backfill can rediscover a valid one
        await db.execute(
            update(Job).where(Job.id == log.job_id).values(
                status=new_job_status,
                hr_email=None,
            )
        )

    # Sync delivery/bounce outcome to hr_emails registry
    _BOUNCE_TYPE_MAP = {
        "hard_bounce": "hard",
        "invalid_email": "hard",
        "soft_bounce": "soft",
        "blocked": "blocked",
        "spam": "spam",
    }
    _bounce_type = _BOUNCE_TYPE_MAP.get(event_type)
    _bounce_reason = event.get("reason") if _bounce_type in ("hard", "blocked") else None

    from services.api.models.hr_email_utils import upsert_hr_email
    await upsert_hr_email(
        session=db,
        tenant_id=log.tenant_id,
        email=log.to_email,
        increment_delivered=(event_type == "delivered"),
        increment_opened=(event_type in ("opened", "first_opening")),
        increment_clicked=(event_type == "click"),
        bounce_type=_bounce_type,
        bounce_reason=_bounce_reason,
    )

    await db.commit()
    logger.info(
        "brevo_webhook_processed",
        event_type=event_type,
        log_id=log.id,
        job_id=log.job_id,
        new_status=new_status,
    )
