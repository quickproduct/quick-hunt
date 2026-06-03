"""Email sending Celery tasks."""
import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog

from services.scraper.celery_app import celery_app
from services.common.async_utils import run_async as _run_async
from services.common.batch_publisher import BatchPublisher
from services.common.logging import log_exception
from services.common.cron_validators import cron_safe
from services.common.placeholder_emails import is_placeholder_email

logger = structlog.get_logger(__name__)

# Statuses that mean "this job already has an active/in-flight send — do NOT send again".
# Terminal statuses (bounced, spam, unsubscribed) are excluded because a job could
# potentially be re-applied to with a corrected email.
_ACTIVE_SEND_STATUSES = frozenset({
    "queued",
    "sent",
    "deferred",       # Brevo is retrying on its own — never create a new send
    "soft_bounced",   # our retry scheduled within cooldown window
    "delivered",      # final success
    "opened",         # final success
    "clicked",        # final success
    # NOTE: "blocked" is NOT here — webhook clears hr_email + sets job=bounced,
    # allowing a future re-send once backfill discovers a valid contact
})


@celery_app.task(
    name="services.sender.tasks.send_application_email_task",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def send_application_email_task(
    self,
    job_id: str,
    candidate_id: str,
    override_email: Optional[str] = None,
    override_subject: Optional[str] = None,
    attach_resume: bool = True,
    dry_run: bool = False,
) -> dict:
    """Full email send pipeline:
    load → verify → dedup-check → render → fetch PDF → send → update DB.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )
    logger.info("send_task_started", job_id=job_id, candidate_id=candidate_id, dry_run=dry_run)

    async def _run():
        from sqlalchemy import select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job, SendLog
        from services.sender.email_adapter import EmailPayload, get_email_adapter
        from services.sender.resume_fetcher import download_resume
        from services.sender.template import render_html, render_plain
        from services.api.core.config import get_settings

        from services.api.core.blacklist_utils import get_blacklisted_names, is_company_blacklisted

        settings = get_settings()
        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            candidate = await session.get(Candidate, candidate_id)

            if not job:
                raise ValueError(f"Job {job_id} not found")
            if not candidate:
                raise ValueError(f"Candidate {candidate_id} not found")

            # ── Deduplication guard ───────────────────────────────────────────
            # Never send if there is already an active/in-flight SendLog for this
            # (job, candidate) pair. This prevents duplicate sends from concurrent
            # workers, rapid retry storms, and accidental double-clicks.
            # dry_run is exempt — it doesn't create a real Brevo send.
            if not dry_run and not override_email:
                existing = await session.execute(
                    select(SendLog.id, SendLog.status).where(
                        SendLog.job_id == job_id,
                        SendLog.candidate_id == candidate_id,
                        SendLog.status.in_(_ACTIVE_SEND_STATUSES),
                    ).limit(1).with_for_update(skip_locked=True)
                )
                row = existing.first()
                if row:
                    logger.info(
                        "send_task_skipped_duplicate",
                        job_id=job_id,
                        candidate_id=candidate_id,
                        existing_log_id=row[0],
                        existing_status=row[1],
                    )
                    return {"status": "skipped", "reason": f"duplicate — active send_log exists ({row[1]})"}

            # Refuse to send to blacklisted companies (defense-in-depth —
            # the scraper already filters at save time, but jobs added before
            # blacklisting or via manual entry are caught here).
            blacklist = await get_blacklisted_names(session)
            if is_company_blacklisted(job.company or "", blacklist):
                logger.info(
                    "send_skipped_blacklisted",
                    job_id=job_id,
                    company=job.company,
                )
                return {"status": "skipped", "reason": "company blacklisted"}

            # Use the actual HR email (or override_email if provided).
            # Set EMAIL_TEST_OVERRIDE in .env to redirect all sends to a test
            # inbox without changing any other logic.
            to_email = override_email or job.hr_email

            # Treat placeholder/junk emails the same as missing — they are not
            # real HR contacts and must not receive applications.
            if to_email and is_placeholder_email(to_email):
                logger.info(
                    "send_skipped_placeholder_email",
                    job_id=job_id,
                    company=job.company,
                    placeholder_email=to_email,
                )
                # Clear the placeholder so fix_placeholder_emails_task can retry discovery
                job.hr_email = None
                await session.commit()
                return {"status": "skipped", "reason": "placeholder email — real HR email not yet discovered"}

            # If no HR email found yet, run inline discovery before giving up.
            if not to_email and not settings.email_test_override:
                from services.scraper.tasks import _discover_email_for_job

                logger.info(
                    "inline_email_discovery_started",
                    job_id=job_id,
                    company=job.company,
                )
                try:
                    discovered_email, resolved_company, resolved_website = (
                        await _discover_email_for_job(
                            job_id=job_id,
                            job_title=job.job_title,
                            company=job.company,
                            job_description=job.job_description,
                            company_website=job.company_website,
                            job_url=job.job_url,
                        )
                    )
                    if discovered_email:
                        to_email = discovered_email
                        # Persist discovered data so backfill doesn't re-run it.
                        job.hr_email = discovered_email
                        if resolved_company and (
                            not job.company or job.company.lower() == "unknown"
                        ):
                            job.company = resolved_company
                        if resolved_website and not job.company_website:
                            job.company_website = resolved_website
                        await session.flush()
                        logger.info(
                            "inline_email_discovered",
                            job_id=job_id,
                            email=to_email,
                        )
                    else:
                        logger.warning(
                            "inline_email_discovery_failed",
                            job_id=job_id,
                            company=job.company,
                        )
                except Exception as exc:
                    logger.warning(
                        "inline_email_discovery_error",
                        job_id=job_id,
                        error=str(exc),
                    )

            if settings.email_test_override:
                to_email = settings.email_test_override
            if not to_email:
                raise ValueError(
                    f"No destination email for job {job_id} — HR email missing "
                    "and inline discovery found nothing."
                )

            subject = override_subject or f"Application for {job.job_title} at {job.company}"

            # MNC jobs always use static_cover_letter regardless of PHP/Python flag.
            # Non-PHP jobs also use static_cover_letter — no PHP/Laravel mentions.
            if (job.source_portal == "mnc_direct" or not job.is_php_python) and candidate.static_cover_letter:
                cover_letter = candidate.static_cover_letter
            elif job.cover_letter:
                cover_letter = job.cover_letter
            elif not job.is_php_python:
                # Non-PHP but no static_cover_letter — generate using non-PHP template
                from services.ai.tasks import _fill_cover_letter
                cover_letter = await _fill_cover_letter(job, candidate)
            else:
                raise ValueError(f"No cover letter for job {job_id}. Generate it first.")

            html_body = render_html(cover_letter, candidate, job)
            plain_body = render_plain(cover_letter, candidate, job)

            # Fetch resume PDF
            resume_bytes: Optional[bytes] = None
            if attach_resume and candidate.resume_url:
                try:
                    resume_bytes = download_resume(candidate.resume_url)
                except Exception as exc:
                    log_exception(logger, "resume_fetch_failed", exc)

            payload = EmailPayload(
                to_email=to_email,
                to_name="Hiring Manager",
                subject=subject,
                html_body=html_body,
                plain_body=plain_body,
                from_email=candidate.email,
                from_name=candidate.name,
                attachment_bytes=resume_bytes,
                attachment_filename=f"{candidate.name.replace(' ', '_')}_resume.pdf",
            )

            # Create send log entry
            log_id = str(uuid.uuid4())
            send_log = SendLog(
                id=log_id,
                job_id=job_id,
                candidate_id=candidate_id,
                to_email=to_email,
                subject=subject,
                body_snippet=plain_body[:500],
                status="queued",
                provider=settings.email_provider,
            )
            session.add(send_log)
            await session.flush()

            if dry_run:
                send_log.status = "dry_run"
                job.status = "cover_generated"
                await session.commit()
                logger.info("send_task_dry_run", job_id=job_id, to=to_email)
                return {
                    "dry_run": True,
                    "to_email": to_email,
                    "subject": subject,
                    "html_preview": html_body[:500],
                }

            # Send via email adapter
            adapter = get_email_adapter()
            message_id = await adapter.send(payload)

            send_log.status = "sent"
            send_log.provider_message_id = message_id
            send_log.sent_at = datetime.now(timezone.utc).replace(tzinfo=None)
            job.status = "sent"
            from services.api.models.hr_email_utils import upsert_hr_email
            await upsert_hr_email(
                session=session,
                tenant_id=job.tenant_id,
                email=to_email,
                increment_send_count=True,
            )
            await session.commit()

        logger.info("send_task_complete", job_id=job_id, message_id=message_id)
        return {"status": "sent", "message_id": message_id, "log_id": log_id}

    try:
        return _run_async(_run())
    except ValueError as exc:
        log_exception(logger, "send_task_validation_failed", exc, job_id=job_id)
        raise
    except RuntimeError as exc:
        if "Brevo error 400" in str(exc) or "Brevo error 422" in str(exc):
            log_exception(logger, "send_task_failed_permanent", exc, job_id=job_id)
            raise ValueError(str(exc))
        log_exception(logger, "send_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)
    except Exception as exc:
        log_exception(logger, "send_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


# ------------------------------------------------------------------ #
# Beat-scheduled dispatcher for ready-to-send jobs                   #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.sender.tasks.dispatch_ready_to_send_task",
)
def dispatch_ready_to_send_task() -> dict:
    """Every 5 min — scans for jobs with cover_letter + hr_email + status=cover_generated
    and dispatches send tasks. Only fires when the tenant has auto_send=True.

    This is the primary pump that drives jobs from 'ready to send' into the email
    send pipeline — without this, ready jobs sit idle and 0 emails get sent.

    NOTE: Not wrapped with @cron_safe because cron_safe uses _run_in_new_thread_with_loop
    which creates a different asyncio event loop than the global _worker_session_factory
    is bound to, causing asyncpg cross-loop errors (SIGSEGV / InterfaceError).
    Duplicate-dispatch protection is provided by the _ACTIVE_SEND_STATUSES dedup
    guard inside send_application_email_task itself.
    """
    # Guard: auto-send is globally disabled
    from services.api.core.config import get_settings
    if not get_settings().auto_send_enabled:
        logger.info("dispatch_ready_to_send_skipped_auto_send_disabled")
        return {"dispatched": 0, "skipped": 0, "reason": "auto_send_disabled"}

    BATCH_SIZE = 50
    logger.info("dispatch_ready_to_send_started")

    async def _run():
        from sqlalchemy import select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job, Tenant

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(Job)
                .where(Job.hr_email.isnot(None))
                .where(Job.cover_letter.isnot(None))
                .where(Job.status == "cover_generated")
                .where(Job.candidate_id.isnot(None))
                .order_by(Job.scraped_at.desc())
                .limit(BATCH_SIZE)
                # No FOR UPDATE needed — we're only reading to dispatch Celery tasks.
                # Duplicate-send protection is in send_application_email_task itself.
            )
            jobs = result.scalars().all()

            # Cache tenant auto_send lookups to avoid N DB queries
            tenant_cache: dict[str, bool] = {}
            dispatched = 0
            skipped = 0

            # Use BatchPublisher to avoid flooding the broker with individual
            # apply_async calls when dispatching many ready-to-send jobs.
            bp = BatchPublisher(chunk_size=50)

            for job in jobs:
                tid = str(job.tenant_id) if job.tenant_id else "__none__"
                if tid not in tenant_cache:
                    if job.tenant_id:
                        tenant = await session.get(Tenant, job.tenant_id)
                        tenant_cache[tid] = bool(tenant and tenant.auto_send)
                    else:
                        # No tenant — treat as auto_send=True (single-tenant setup)
                        tenant_cache[tid] = True

                if not tenant_cache[tid]:
                    skipped += 1
                    continue

                bp.add(send_application_email_task.s(job.id, job.candidate_id))
                dispatched += 1

            if dispatched > 0:
                bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)

        logger.info(
            "dispatch_ready_to_send_complete",
            dispatched=dispatched,
            skipped=skipped,
        )
        return {"dispatched": dispatched, "skipped": skipped}

    return _run_async(_run())


# ------------------------------------------------------------------ #
# Beat-scheduled auto-approver for pending_approval jobs             #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.sender.tasks.auto_approve_pending_jobs_task",
)
def auto_approve_pending_jobs_task() -> dict:
    """Every 10 min — finds jobs stuck in pending_approval that have both an HR email
    and cover letter, and dispatches send tasks for tenants where auto_send=True.

    Jobs land in pending_approval when the LangGraph workflow runs before the tenant's
    auto_send flag is consulted. This task unblocks them.

    NOTE: Not wrapped with @cron_safe — see dispatch_ready_to_send_task docstring.
    """
    # Guard: auto-send is globally disabled
    from services.api.core.config import get_settings
    if not get_settings().auto_send_enabled:
        logger.info("auto_approve_skipped_auto_send_disabled")
        return {"dispatched": 0, "skipped": 0, "reason": "auto_send_disabled"}

    BATCH_SIZE = 50
    logger.info("auto_approve_pending_jobs_started")

    async def _run():
        from sqlalchemy import select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job, Tenant

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            result = await session.execute(
                select(Job)
                .where(Job.status == "pending_approval")
                .where(Job.hr_email.isnot(None))
                .where(Job.cover_letter.isnot(None))
                .where(Job.candidate_id.isnot(None))
                .order_by(Job.scraped_at.desc())
                .limit(BATCH_SIZE)
                # No FOR UPDATE — we only read to dispatch Celery tasks.
                # Dedup is handled inside send_application_email_task.
            )
            jobs = result.scalars().all()

            tenant_cache: dict[str, bool] = {}
            dispatched = 0
            skipped = 0

            # Use BatchPublisher to avoid flooding the broker with individual
            # apply_async calls when approving many pending jobs at once.
            bp = BatchPublisher(chunk_size=50)

            for job in jobs:
                tid = str(job.tenant_id) if job.tenant_id else "__none__"
                if tid not in tenant_cache:
                    if job.tenant_id:
                        tenant = await session.get(Tenant, job.tenant_id)
                        tenant_cache[tid] = bool(tenant and tenant.auto_send)
                    else:
                        tenant_cache[tid] = True

                if not tenant_cache[tid]:
                    skipped += 1
                    continue

                bp.add(send_application_email_task.s(job.id, job.candidate_id))
                dispatched += 1

            if dispatched > 0:
                bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)

        logger.info(
            "auto_approve_pending_jobs_complete",
            dispatched=dispatched,
            skipped=skipped,
        )
        return {"dispatched": dispatched, "skipped": skipped}

    return _run_async(_run())


# ------------------------------------------------------------------ #
# Beat-scheduled retry for failed sends                               #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.sender.tasks.retry_failed_sends_task",
)
@cron_safe(
    task_name="retry_failed_sends_task",
    singleton_ttl_seconds=600,  # 10 min - matches cron interval
    max_runs_per_hour=6,  # Every 10 min = 6/hour
    max_queue_depth=1000,  # Don't retry if email queue is backed up
    circuit_failure_threshold=5,
    circuit_recovery_seconds=1800,
)
def retry_failed_sends_task() -> dict:
    """Retry temporary email failures using per-status cool-down windows.

    Status          | Retry window | Max retries | Reason
    --------------- | ------------ | ----------- | -------------------------------------------
    soft_bounced    | 48 hours     | 3           | Mailbox full / temporary server reject
    blocked         | 48 hours     | 3           | Sending IP/domain blocked, retry later

    NOTE: 'deferred' is intentionally NOT in this table.
    Deferred means Brevo's relay already accepted the message and is retrying delivery
    internally. Creating a new Brevo API call on top would cause duplicate sends.
    We wait for Brevo's webhook to report the final outcome (delivered / soft_bounce /
    hard_bounce) before taking any further action.
    """
    # Guard: auto-send is globally disabled
    from services.api.core.config import get_settings
    if not get_settings().auto_send_enabled:
        logger.info("retry_failed_sends_skipped_auto_send_disabled")
        return {"dispatched": 0, "skipped": 0, "reason": "auto_send_disabled"}

    # (retry_after_hours, max_retries)
    # blocked is NOT retried — Brevo defines it as permanent (spam complaints +
    # repeated hard bounces). Webhook handler clears hr_email + sets job=bounced.
    RETRY_POLICY: dict[str, tuple[float, int]] = {
        "soft_bounced": (48.0, 3),   # mailbox full / server temporarily unavailable
    }

    logger.info("retry_failed_sends_started", policies=list(RETRY_POLICY.keys()))

    async def _run():
        from datetime import timedelta

        from sqlalchemy import select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import SendLog

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            # SELECT FOR UPDATE SKIP LOCKED prevents two concurrent instances of
            # this task (from multiple email worker replicas) from processing the
            # same send_log rows simultaneously and dispatching duplicate sends.
            result = await session.execute(
                select(SendLog)
                .where(SendLog.status.in_(list(RETRY_POLICY.keys())))
                .order_by(SendLog.sent_at.asc())
                .limit(50)
                .with_for_update(skip_locked=True)
            )
            logs = result.scalars().all()

            dispatched = 0
            skipped = 0
            for log in logs:
                if not log.job_id or not log.candidate_id:
                    continue

                retry_after_h, max_retries = RETRY_POLICY[log.status]

                # Respect max retries for this status
                if (log.retry_count or 0) >= max_retries:
                    # Mark as permanently failed so it leaves the retry queue
                    log.status = "bounced"
                    log.error_message = f"Exhausted {max_retries} retries (was {log.status})"
                    skipped += 1
                    continue

                # Enforce cool-down: only retry after retry_after_h since last send
                last_attempt = log.sent_at
                if last_attempt:
                    elapsed = (now - last_attempt).total_seconds() / 3600
                    if elapsed < retry_after_h:
                        skipped += 1
                        continue

                # Increment retry_count and commit BEFORE dispatching so that
                # even if the worker crashes after dispatch, we don't retry again
                # immediately on the next beat tick.
                log.retry_count = (log.retry_count or 0) + 1
                log.sent_at = now  # reset cooldown clock for this retry attempt
                await session.flush()

                send_application_email_task.apply_async(
                    args=[log.job_id, log.candidate_id],
                    countdown=5,
                    ignore_result=True,
                )
                dispatched += 1

            await session.commit()

        logger.info("retry_failed_sends_complete", dispatched=dispatched, skipped=skipped)
        return {"dispatched": dispatched, "skipped": skipped}

    return _run_async(_run())
