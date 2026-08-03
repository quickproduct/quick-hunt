"""Send router — email sending and send log listing."""
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog

logger = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_get, cache_set
from services.api.core.config import get_settings
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_data_user
from services.api.models.db import Candidate, DirectSendLog, Job, SendLog, User
from services.scraper.celery_app import celery_app
from services.api.schemas.schemas import SendLogEnrichedOut, SendRequest
from services.common.placeholder_emails import is_placeholder_email

_SEND_LOGS_CACHE_TTL = 30  # seconds

router = APIRouter(tags=["send"])
Auth = Annotated[User, Depends(get_current_data_user)]


@router.post("/jobs/{job_id}/send")
async def send_application(
    job_id: str, body: SendRequest, current_user: Auth, db: AsyncSession = Depends(get_db)
):
    """Queue or immediately send an application email."""
    job = await db.scalar(
        select(Job).where(Job.id == job_id).with_for_update()
    )
    if not job or job.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Job not found")

    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate or candidate.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    to_email = body.override_email or job.hr_email
    if not to_email:
        raise HTTPException(
            status_code=422,
            detail="Job has no HR email. Run email discovery first or provide override_email.",
        )

    # Reject junk/role inboxes before publishing a task. Previously the API
    # returned a successful queue response and the worker rejected the address
    # later, which made a blocked send look like a delivered application.
    if not body.dry_run and is_placeholder_email(str(to_email)):
        if not body.override_email and job.hr_email == to_email:
            job.hr_email = None
            await db.commit()
        logger.warning(
            "application_send_rejected_placeholder_email",
            job_id=job_id,
            candidate_id=body.candidate_id,
            to_email=str(to_email),
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"{to_email} is not a valid recruiter inbox. "
                "Run HR email discovery or provide a verified recruiter email."
            ),
        )

    cover_letter = (body.cover_letter or "").strip() or None

    if not cover_letter and not job.cover_letter and not body.dry_run:
        raise HTTPException(
            status_code=422,
            detail="Job has no cover letter. Generate one first with POST /jobs/{id}/generate_cover.",
        )

    if not cover_letter and job.cover_letter and str(job.candidate_id or "") != body.candidate_id:
        raise HTTPException(
            status_code=422,
            detail="This cover letter was generated for a different candidate. Generate a new cover letter for the selected candidate before sending.",
        )

    # Block only if this candidate already has an active send to this address.
    # Locking the job row makes the check + reservation atomic on PostgreSQL.
    if not body.dry_run:
        from sqlalchemy import exists
        from services.sender.tasks import _ACTIVE_SEND_STATUSES
        already_sent = await db.scalar(
            select(exists().where(
                SendLog.job_id == job_id,
                SendLog.candidate_id == body.candidate_id,
                SendLog.to_email == to_email,
                SendLog.status.in_(_ACTIVE_SEND_STATUSES),
            ))
        )
        if already_sent:
            raise HTTPException(
                status_code=422,
                detail="You have already sent an application for this job.",
            )

    if body.dry_run:
        from services.sender.template import render_html, render_plain
        preview_cover = cover_letter or job.cover_letter or "Sample cover letter"
        html = render_html(preview_cover, candidate, job)
        plain = render_plain(preview_cover, candidate, job)
        return {
            "dry_run": True,
            "to_email": to_email,
            "subject": body.override_subject or f"Application for {job.job_title} at {job.company}",
            "html_preview": html[:1000],
            "plain_preview": plain[:500],
        }

    settings = get_settings()
    send_log = SendLog(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        job_id=job_id,
        candidate_id=body.candidate_id,
        to_email=settings.email_test_override or str(to_email),
        subject=body.override_subject or f"Application for {job.job_title} at {job.company}",
        body_snippet=(cover_letter or job.cover_letter or "")[:500],
        status="queued",
        provider=settings.email_provider,
    )
    db.add(send_log)
    await db.commit()

    try:
        task = celery_app.send_task(
            "services.sender.tasks.send_application_email_task",
            kwargs={
                "job_id": job_id,
                "candidate_id": body.candidate_id,
                "override_email": str(body.override_email) if body.override_email else None,
                "override_subject": body.override_subject,
                "cover_letter_override": cover_letter,
                "attach_resume": body.attach_resume,
                "dry_run": False,
                "send_log_id": send_log.id,
            },
            queue="jh_email_send",
            ignore_result=True,
        )
    except Exception as exc:
        send_log.status = "failed"
        send_log.error_message = str(exc)[:1000]
        await db.commit()
        logger.exception(
            "application_send_queue_failed",
            job_id=job_id,
            candidate_id=body.candidate_id,
            send_log_id=send_log.id,
        )
        raise HTTPException(status_code=503, detail="Email queue unavailable. Please retry.")

    logger.info(
        "application_send_queued",
        job_id=job_id,
        candidate_id=body.candidate_id,
        send_log_id=send_log.id,
        celery_task_id=task.id,
    )
    return {
        "message": "Email send queued",
        "celery_task_id": task.id,
        "send_log_id": send_log.id,
        "job_id": job_id,
    }


@router.post("/jobs/{job_id}/approve")
async def approve_application(
    job_id: str,
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    """Approve a pending application and durably queue its email send."""
    from sqlalchemy import update

    job = await db.scalar(
        select(Job).where(
            Job.id == job_id,
            Job.tenant_id == current_user.tenant_id,
        ).with_for_update()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Job is not pending approval")
    if not job.candidate_id or not job.hr_email or not job.cover_letter:
        raise HTTPException(
            status_code=422,
            detail="Approval requires a candidate, HR email, and cover letter.",
        )
    if is_placeholder_email(job.hr_email):
        rejected_email = job.hr_email
        job.hr_email = None
        await db.commit()
        logger.warning(
            "application_approval_rejected_placeholder_email",
            job_id=job.id,
            candidate_id=job.candidate_id,
            to_email=rejected_email,
        )
        raise HTTPException(
            status_code=422,
            detail=(
                f"{rejected_email} is not a valid recruiter inbox. "
                "Run HR email discovery or provide a verified recruiter email."
            ),
        )
    candidate = await db.get(Candidate, job.candidate_id)
    if not candidate or candidate.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    transition = await db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == "pending_approval")
        .values(status="sending")
    )
    if transition.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Job approval is already in progress")

    settings = get_settings()
    send_log = SendLog(
        id=str(uuid.uuid4()),
        tenant_id=current_user.tenant_id,
        job_id=job.id,
        candidate_id=job.candidate_id,
        to_email=settings.email_test_override or job.hr_email,
        subject=f"Application for {job.job_title} at {job.company}",
        body_snippet=job.cover_letter[:500],
        status="queued",
        provider=settings.email_provider,
    )
    db.add(send_log)
    await db.commit()

    try:
        task = celery_app.send_task(
            "services.sender.tasks.send_application_email_task",
            kwargs={
                "job_id": job.id,
                "candidate_id": job.candidate_id,
                "attach_resume": True,
                "dry_run": False,
                "send_log_id": send_log.id,
            },
            queue="jh_email_send",
            ignore_result=True,
        )
    except Exception as exc:
        send_log.status = "failed"
        send_log.error_message = str(exc)[:1000]
        job.status = "pending_approval"
        await db.commit()
        logger.exception(
            "application_approval_queue_failed",
            job_id=job.id,
            send_log_id=send_log.id,
        )
        raise HTTPException(status_code=503, detail="Email queue unavailable. Please retry.")

    logger.info(
        "application_approved_and_queued",
        job_id=job.id,
        candidate_id=job.candidate_id,
        send_log_id=send_log.id,
        celery_task_id=task.id,
        approved_by=current_user.id,
    )
    return {
        "status": "sending",
        "job_id": job.id,
        "send_log_id": send_log.id,
        "celery_task_id": task.id,
    }


MAX_DIRECT_SEND_EMAILS = 1000


class DirectSendRequest(BaseModel):
    candidate_id: str
    hr_emails: list[EmailStr] = Field(
        ..., min_length=1, max_length=MAX_DIRECT_SEND_EMAILS
    )


class DirectSendResult(BaseModel):
    sent: int
    queued: int = 0
    failed: list[str] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    celery_task_ids: list[str] = Field(default_factory=list)


@router.post("/direct-send", response_model=DirectSendResult)
async def direct_hr_send(
    body: DirectSendRequest, current_user: Auth, db: AsyncSession = Depends(get_db)
):
    """Queue resume + static cover letter sends for a list of HR email addresses."""
    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate or candidate.tenant_id != current_user.tenant_id:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.static_cover_letter:
        raise HTTPException(
            status_code=422,
            detail="Candidate has no static cover letter. Add one in the Candidates page first.",
        )

    hr_emails = list(
        dict.fromkeys(str(e).strip().lower() for e in body.hr_emails if str(e).strip())
    )
    if not hr_emails:
        raise HTTPException(status_code=422, detail="No HR email addresses provided")

    tenant_id = current_user.tenant_id
    existing_rows = await db.scalars(
        select(DirectSendLog).where(
            DirectSendLog.tenant_id == tenant_id,
            DirectSendLog.candidate_id == body.candidate_id,
            DirectSendLog.hr_email.in_(hr_emails),
        )
    )
    existing_by_email = {row.hr_email: row for row in existing_rows.all()}
    active_statuses = {"queued", "sending", "sent"}
    skipped = [
        email for email in hr_emails
        if email in existing_by_email and existing_by_email[email].status in active_statuses
    ]
    emails_to_send = [email for email in hr_emails if email not in set(skipped)]

    task_ids: list[str] = []
    failed: list[str] = []
    logs_to_enqueue: list[DirectSendLog] = []
    settings = get_settings()

    for hr_email in emails_to_send:
        existing_log = existing_by_email.get(hr_email)
        if existing_log:
            existing_log.status = "queued"
            existing_log.provider = settings.email_provider
            existing_log.provider_message_id = None
            existing_log.celery_task_id = None
            existing_log.error_message = None
            existing_log.sent_at = None
            logs_to_enqueue.append(existing_log)
            continue

        direct_log = DirectSendLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            candidate_id=body.candidate_id,
            hr_email=hr_email,
            status="queued",
            provider=settings.email_provider,
        )
        db.add(direct_log)
        logs_to_enqueue.append(direct_log)

    await db.commit()

    for direct_log in logs_to_enqueue:
        try:
            task = celery_app.send_task(
                "services.sender.tasks.send_direct_hr_email_task",
                args=[direct_log.id],
                queue="jh_email_send",
                ignore_result=True,
            )
            direct_log.celery_task_id = task.id
            task_ids.append(task.id)
        except Exception as exc:
            direct_log.status = "failed"
            direct_log.error_message = str(exc)[:1000]
            logger.warning(
                "direct_send_queue_failed",
                candidate_id=body.candidate_id,
                hr_email=direct_log.hr_email,
                error=str(exc),
            )
            failed.append(f"{direct_log.hr_email}: {str(exc)[:100]}")

    await db.commit()

    logger.info(
        "direct_send_queued",
        candidate_id=body.candidate_id,
        tenant_id=tenant_id,
        queued=len(task_ids),
        failed=len(failed),
        skipped=len(skipped),
    )
    return DirectSendResult(
        sent=0,
        queued=len(task_ids),
        failed=failed,
        skipped=skipped,
        celery_task_ids=task_ids,
    )


@router.get("/jobs/send_logs", response_model=list[SendLogEnrichedOut])
async def list_send_logs(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
    job_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=500),
):
    tenant_id = current_user.tenant_id
    cache_key = f"send_logs:{tenant_id}:{job_id or 'all'}:{status or 'all'}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return [SendLogEnrichedOut(**row) for row in cached]

    q = (
        select(SendLog, Job.job_title, Job.company)
        .outerjoin(Job, SendLog.job_id == Job.id)
        .where(SendLog.tenant_id == tenant_id)
        .order_by(SendLog.sent_at.desc().nullslast())
        .limit(limit)
    )
    if job_id:
        q = q.where(SendLog.job_id == job_id)
    if status:
        q = q.where(SendLog.status == status)

    result = await db.execute(q)
    rows = result.all()

    output = []
    for send_log, job_title, company in rows:
        data = SendLogEnrichedOut.model_validate(send_log)
        data.job_title = job_title
        data.company = company
        output.append(data)

    asyncio.ensure_future(
        cache_set(cache_key, [row.model_dump(mode="json") for row in output], _SEND_LOGS_CACHE_TTL)
    )
    return output
