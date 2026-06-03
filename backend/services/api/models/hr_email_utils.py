"""Shared upsert helper for the hr_emails registry table.

Imported by all sync points:
  - services.api.routers.jobs       (manual PATCH /{job_id}/hr-email)
  - services.api.routers.webhooks   (bounce/blocked/spam/delivered events)
  - services.sender.tasks           (post-send increment)
  - services.scraper.tasks          (scrape-time hr_email capture + backfill)
  - services.api.tasks.hr_email_tasks (one-time backfill Celery task)
"""
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.models.db import HrEmail


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _extract_domain(email: str) -> str:
    return email.lower().strip().rsplit("@", 1)[-1]


async def upsert_hr_email(
    session: AsyncSession,
    tenant_id: str,
    email: str,
    *,
    increment_job_count: bool = False,
    increment_send_count: bool = False,
    increment_delivered: bool = False,
    increment_opened: bool = False,
    increment_clicked: bool = False,
    bounce_type: Optional[str] = None,    # "hard" | "soft" | "blocked" | "spam"
    bounce_reason: Optional[str] = None,
) -> HrEmail:
    """Create or update an HrEmail record.

    Does NOT call session.commit() — callers own their transaction boundary.
    """
    from services.common.placeholder_emails import is_placeholder_email

    email_lower = email.lower().strip()
    domain = _extract_domain(email_lower)
    now = _utcnow()
    is_ph = is_placeholder_email(email_lower)

    result = await session.execute(
        select(HrEmail).where(
            HrEmail.tenant_id == tenant_id,
            HrEmail.email == email_lower,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = HrEmail(
            tenant_id=tenant_id,
            email=email_lower,
            domain=domain,
            is_placeholder=is_ph,
            validation_status="fake" if is_ph else "unknown",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(record)
    else:
        record.last_seen_at = now

    if increment_job_count:
        record.job_count = (record.job_count or 0) + 1
    if increment_send_count:
        record.send_count = (record.send_count or 0) + 1
        record.last_send_at = now
    if increment_delivered:
        record.delivered_count = (record.delivered_count or 0) + 1
    if increment_opened:
        record.opened_count = (record.opened_count or 0) + 1
    if increment_clicked:
        record.clicked_count = (record.clicked_count or 0) + 1

    if bounce_type:
        record.last_bounce_at = now
        record.last_bounce_type = bounce_type
        if bounce_reason:
            record.last_bounce_reason = bounce_reason

        if bounce_type == "hard":
            record.hard_bounce_count = (record.hard_bounce_count or 0) + 1
            record.validation_status = "bounced"
        elif bounce_type == "soft":
            record.soft_bounce_count = (record.soft_bounce_count or 0) + 1
        elif bounce_type == "blocked":
            record.blocked_count = (record.blocked_count or 0) + 1
            record.validation_status = "bounced"
        elif bounce_type == "spam":
            record.spam_count = (record.spam_count or 0) + 1
            record.validation_status = "bounced"

    # Mark valid if delivered with no hard bounces
    if increment_delivered and (record.hard_bounce_count or 0) == 0 and (record.blocked_count or 0) == 0:
        if record.validation_status in ("unknown",):
            record.validation_status = "valid"

    await session.flush()
    return record
