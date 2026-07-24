"""Send router — email sending and send log listing."""
import asyncio
from datetime import datetime, timezone
from typing import Annotated, Optional

import structlog

logger = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_get, cache_set
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import Candidate, DirectSendLog, Job, SendLog, User
from services.scraper.celery_app import celery_app
from services.api.schemas.schemas import SendLogEnrichedOut, SendRequest

_SEND_LOGS_CACHE_TTL = 30  # seconds

router = APIRouter(tags=["send"])
Auth = Annotated[User, Depends(get_current_user)]


@router.post("/jobs/{job_id}/send")
async def send_application(
    job_id: str, body: SendRequest, _: Auth, db: AsyncSession = Depends(get_db)
):
    """Queue or immediately send an application email."""
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    to_email = body.override_email or job.hr_email
    if not to_email:
        raise HTTPException(
            status_code=422,
            detail="Job has no HR email. Run email discovery first or provide override_email.",
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

    # Block only if THIS candidate already sent to this job — not if a different candidate did.
    if not body.dry_run:
        from sqlalchemy import exists
        already_sent = await db.scalar(
            select(exists().where(
                SendLog.job_id == job_id,
                SendLog.candidate_id == body.candidate_id,
                SendLog.status == "sent",
            ))
        )
        if already_sent:
            raise HTTPException(
                status_code=422,
                detail="You have already sent an application for this job.",
            )

    from services.sender.tasks import send_application_email_task

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

    task = celery_app.send_task(
        "services.sender.tasks.send_application_email_task",
        kwargs={
            "job_id": job_id,
            "candidate_id": body.candidate_id,
            "override_email": body.override_email,
            "override_subject": body.override_subject,
            "cover_letter_override": cover_letter,
            "attach_resume": body.attach_resume,
            "dry_run": False,
        },
        queue="jh_email_send",
        ignore_result=True,
    )

    return {"message": "Email send queued", "celery_task_id": task.id, "job_id": job_id}


class DirectSendRequest(BaseModel):
    candidate_id: str
    hr_emails: list[str]


class DirectSendResult(BaseModel):
    sent: int
    queued: int = 0
    failed: list[str]
    skipped: list[str] = []
    celery_task_ids: list[str] = []


@router.post("/direct-send", response_model=DirectSendResult)
async def direct_hr_send(
    body: DirectSendRequest, current_user: Auth, db: AsyncSession = Depends(get_db)
):
    """Queue resume + static cover letter sends for a list of HR email addresses."""
    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.static_cover_letter:
        raise HTTPException(
            status_code=422,
            detail="Candidate has no static cover letter. Add one in the Candidates page first.",
        )

    hr_emails = list(dict.fromkeys(e.strip().lower() for e in body.hr_emails if e.strip()))
    if not hr_emails:
        raise HTTPException(status_code=422, detail="No HR email addresses provided")

    tenant_id = current_user.tenant_id
    already_sent_rows = await db.scalars(
        select(DirectSendLog.hr_email).where(
            DirectSendLog.tenant_id == tenant_id,
            DirectSendLog.candidate_id == body.candidate_id,
            DirectSendLog.hr_email.in_(hr_emails),
        )
    )
    already_sent_set = set(already_sent_rows.all())
    emails_to_send = [e for e in hr_emails if e not in already_sent_set]
    skipped = list(already_sent_set & set(hr_emails))

    task_ids: list[str] = []
    failed: list[str] = []

    for hr_email in emails_to_send:
        try:
            task = celery_app.send_task(
                "services.sender.tasks.send_direct_hr_email_task",
                args=[body.candidate_id, hr_email, tenant_id],
                queue="jh_email_send",
                ignore_result=True,
            )
            task_ids.append(task.id)
        except Exception as exc:
            logger.warning(
                "direct_send_queue_failed",
                candidate_id=body.candidate_id,
                hr_email=hr_email,
                error=str(exc),
            )
            failed.append(f"{hr_email}: {str(exc)[:100]}")

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
    _: Auth,
    db: AsyncSession = Depends(get_db),
    job_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=500),
):
    cache_key = f"send_logs:{job_id or 'all'}:{status or 'all'}:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return [SendLogEnrichedOut(**row) for row in cached]

    q = (
        select(SendLog, Job.job_title, Job.company)
        .outerjoin(Job, SendLog.job_id == Job.id)
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
