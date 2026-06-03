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

    if not job.cover_letter and not body.dry_run:
        raise HTTPException(
            status_code=422,
            detail="Job has no cover letter. Generate one first with POST /jobs/{id}/generate_cover.",
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
        html = render_html(job.cover_letter or "Sample cover letter", candidate, job)
        plain = render_plain(job.cover_letter or "Sample cover letter", candidate, job)
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
    failed: list[str]
    skipped: list[str] = []


@router.post("/direct-send", response_model=DirectSendResult)
async def direct_hr_send(
    body: DirectSendRequest, current_user: Auth, db: AsyncSession = Depends(get_db)
):
    """Send resume + static cover letter directly to a list of HR email addresses."""
    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not candidate.static_cover_letter:
        raise HTTPException(
            status_code=422,
            detail="Candidate has no static cover letter. Add one in the Candidates page first.",
        )

    hr_emails = [e.strip().lower() for e in body.hr_emails if e.strip()]
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

    if not emails_to_send:
        return DirectSendResult(sent=0, failed=[], skipped=skipped)

    from services.sender.template import render_html, render_plain
    from services.sender.email_adapter import EmailPayload, get_email_adapter
    from services.sender.resume_fetcher import download_resume as fetch_resume

    html_body = render_html(candidate.static_cover_letter, candidate, None)
    plain_body = render_plain(candidate.static_cover_letter, candidate, None)
    subject = f"Application from {candidate.name}"

    attachment_bytes: Optional[bytes] = None
    if candidate.resume_url:
        try:
            attachment_bytes = fetch_resume(candidate.resume_url)
        except Exception as exc:
            logger.warning("resume_fetch_failed_direct_send", error=str(exc))
            attachment_bytes = None

    safe_name = candidate.name.lower().replace(" ", "-")
    attachment_filename = f"{safe_name}-resume.pdf"

    adapter = get_email_adapter()
    sent_count = 0
    failed: list[str] = []

    for hr_email in emails_to_send:
        payload = EmailPayload(
            to_email=hr_email,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            from_email=candidate.email,
            from_name=candidate.name,
            attachment_bytes=attachment_bytes,
            attachment_filename=attachment_filename,
        )
        try:
            await adapter.send(payload)
            db.add(DirectSendLog(
                tenant_id=tenant_id,
                candidate_id=body.candidate_id,
                hr_email=hr_email,
            ))
            sent_count += 1
        except Exception as exc:
            failed.append(f"{hr_email}: {str(exc)[:100]}")

    await db.commit()
    return DirectSendResult(sent=sent_count, failed=failed, skipped=skipped)


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
