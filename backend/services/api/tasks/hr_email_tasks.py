"""HR email registry Celery tasks.

  - backfill_hr_emails_registry_task: one-time population from existing jobs + send_logs
  - validate_mx_task: async DNS MX lookup for a single email's domain
"""
import structlog

from services.common.async_utils import run_async as _run_async
from services.scraper.celery_app import celery_app

logger = structlog.get_logger(__name__)


@celery_app.task(
    name="services.api.tasks.hr_email_tasks.backfill_hr_emails_registry_task",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
)
def backfill_hr_emails_registry_task(self, tenant_id: str) -> dict:
    """Populate hr_emails from all distinct non-null hr_email values in the jobs table.

    Processes in batches of 500. Safe to run multiple times — upsert is idempotent.
    Back-fills send_count, delivered_count, and hard_bounce_count from send_logs.
    """
    logger.info("hr_email_backfill_started", tenant_id=tenant_id)

    async def _run():
        from sqlalchemy import distinct, func, select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job, SendLog
        from services.api.models.hr_email_utils import upsert_hr_email

        session_factory = get_worker_session_factory()
        BATCH = 500
        last_email: str | None = None
        total = 0

        while True:
            async with session_factory() as session:
                q = (
                    select(distinct(Job.hr_email).label("hr_email"))
                    .where(
                        Job.tenant_id == tenant_id,
                        Job.hr_email.isnot(None),
                    )
                )
                if last_email is not None:
                    q = q.where(Job.hr_email > last_email)
                q = q.order_by(Job.hr_email).limit(BATCH)
                rows = (await session.execute(q)).all()

            if not rows:
                break
            last_email = rows[-1].hr_email

            async with session_factory() as session:
                for row in rows:
                    email = row.hr_email
                    tid = tenant_id

                    job_count = (await session.execute(
                        select(func.count()).select_from(Job).where(
                            Job.tenant_id == tid,
                            Job.hr_email == email,
                        )
                    )).scalar_one()

                    send_count = (await session.execute(
                        select(func.count()).select_from(SendLog).where(
                            SendLog.tenant_id == tid,
                            SendLog.to_email == email,
                        )
                    )).scalar_one()

                    delivered = (await session.execute(
                        select(func.count()).select_from(SendLog).where(
                            SendLog.tenant_id == tid,
                            SendLog.to_email == email,
                            SendLog.status == "delivered",
                        )
                    )).scalar_one()

                    hard_bounces = (await session.execute(
                        select(func.count()).select_from(SendLog).where(
                            SendLog.tenant_id == tid,
                            SendLog.to_email == email,
                            SendLog.status == "bounced",
                        )
                    )).scalar_one()

                    record = await upsert_hr_email(session=session, tenant_id=tid, email=email)
                    record.job_count = job_count
                    record.send_count = send_count
                    record.delivered_count = delivered
                    record.hard_bounce_count = hard_bounces
                    if hard_bounces > 0:
                        record.validation_status = "bounced"
                    total += 1

                await session.commit()

            logger.info("hr_email_backfill_progress", last_email=last_email, total=total)

        logger.info("hr_email_backfill_complete", total=total)
        return {"backfilled": total}

    return _run_async(_run())


@celery_app.task(
    name="services.api.tasks.hr_email_tasks.validate_mx_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def validate_mx_task(self, email_id: str) -> dict:
    """Perform DNS MX lookup for the domain of an HrEmail record.

    Updates mx_valid, mx_checked_at, and transitions validation_status
    from unknown → valid/invalid based on DNS result.
    """
    logger.info("mx_validate_started", email_id=email_id)

    async def _run():
        from datetime import datetime, timezone
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import HrEmail

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            record = await session.get(HrEmail, email_id)
            if not record:
                logger.warning("mx_validate_no_record", email_id=email_id)
                return {"status": "not_found"}

            domain = record.domain
            mx_valid = await _check_mx(domain)
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            record.mx_valid = mx_valid
            record.mx_checked_at = now

            if mx_valid is False and record.validation_status == "unknown":
                record.validation_status = "invalid"
            elif mx_valid is True and record.validation_status == "unknown":
                record.validation_status = "valid"

            await session.commit()
            logger.info("mx_validate_complete", email_id=email_id, domain=domain, mx_valid=mx_valid)
            return {"domain": domain, "mx_valid": mx_valid}

    return _run_async(_run())


@celery_app.task(
    name="services.api.tasks.hr_email_tasks.revalidate_hr_emails_task",
    bind=True,
    max_retries=1,
    default_retry_delay=120,
)
def revalidate_hr_emails_task(self, tenant_id: str, limit: int = 2000) -> dict:
    """One-shot re-validation of the hr_emails registry.

    Walks rows with validation_status in (unknown, valid) where bounces
    have occurred, plus all status='unknown' rows, and re-probes each
    via SMTP (tri-state). Definitive 5xx → 'invalid'. Confirmed 2xx →
    'valid'. Inconclusive results are left untouched.

    Trigger once via admin MCP after the verification-only HR pipeline
    is deployed; cleans existing fake/stale data so the sender stops
    bouncing on it.
    """
    logger.info("hr_email_revalidate_started", tenant_id=tenant_id, limit=limit)

    async def _run():
        from sqlalchemy import or_, select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import HrEmail
        from services.common.placeholder_emails import is_placeholder_email
        from services.scraper.tasks import (
            SMTP_REJECTED,
            SMTP_VERIFIED,
            _smtp_probe_email,
        )

        session_factory = get_worker_session_factory()
        marked_invalid = 0
        marked_valid = 0
        marked_fake = 0
        inconclusive = 0

        async with session_factory() as session:
            rows = (await session.execute(
                select(HrEmail)
                .where(
                    HrEmail.tenant_id == tenant_id,
                    or_(
                        HrEmail.validation_status == "unknown",
                        HrEmail.hard_bounce_count > 0,
                        HrEmail.blocked_count > 0,
                    ),
                )
                .limit(limit)
            )).scalars().all()

            for record in rows:
                if is_placeholder_email(record.email):
                    record.validation_status = "fake"
                    record.is_placeholder = True
                    marked_fake += 1
                    continue

                domain = record.domain or record.email.rsplit("@", 1)[-1]
                result = await _smtp_probe_email(record.email, domain)
                if result == SMTP_REJECTED:
                    record.validation_status = "invalid"
                    marked_invalid += 1
                elif result == SMTP_VERIFIED:
                    if record.validation_status == "unknown":
                        record.validation_status = "valid"
                        marked_valid += 1
                else:
                    inconclusive += 1

            await session.commit()

        summary = {
            "scanned": len(rows),
            "marked_invalid": marked_invalid,
            "marked_valid": marked_valid,
            "marked_fake": marked_fake,
            "inconclusive": inconclusive,
        }
        logger.info("hr_email_revalidate_complete", **summary)
        return summary

    return _run_async(_run())


async def _check_mx(domain: str) -> bool:
    """Return True if the domain has at least one MX record, False otherwise."""
    try:
        import aiodns
        resolver = aiodns.DNSResolver()
        result = await resolver.query(domain, "MX")
        return bool(result)
    except ImportError:
        pass
    except Exception:
        return False

    try:
        import asyncio
        import dns.resolver

        def _sync_mx():
            try:
                answers = dns.resolver.resolve(domain, "MX", lifetime=3.0)
                return bool(answers)
            except Exception:
                return False

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _sync_mx)
    except Exception:
        return False
