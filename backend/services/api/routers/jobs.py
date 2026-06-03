"""Jobs router — list, filter, detail, status update, cover letter generation, bulk ops."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_delete, cache_get, cache_set
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import BlacklistedCompany, Candidate, Job, User
from services.api.schemas.schemas import (
    BulkGenerateCoverRequest,
    BulkSendRequest,
    BulkSendResponse,
    GenerateCoverRequest,
    HrEmailUpdate,
    JobOut,
    JobStatusUpdate,
    JobTimeline,
    SkippedJob,
    TimelineEvent,
)
from services.scraper.celery_app import celery_app

_JOBS_CACHE_TTL = 10   # seconds — short enough to feel live, long enough to absorb bursts
_COUNT_CACHE_TTL = 10


def _list_cache_key(**params) -> str:
    return "jobs:list:" + hashlib.md5(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()


def _count_cache_key(**params) -> str:
    return "jobs:count:" + hashlib.md5(
        json.dumps(params, sort_keys=True, default=str).encode()
    ).hexdigest()

router = APIRouter(prefix="/jobs", tags=["jobs"])
Auth = Annotated[User, Depends(get_current_user)]


def _apply_job_filters(
    q,
    status: Optional[str],
    portal: Optional[str],
    company: Optional[str],
    has_hr_email: Optional[bool],
    min_score: Optional[float],
    search: Optional[str],
    max_score: Optional[float],
    has_cover: Optional[bool],
    job_type: Optional[str],
    has_active_send: Optional[bool] = None,
    scraped_after: Optional[str] = None,
    posted_after: Optional[str] = None,
    mnc_only: Optional[bool] = None,
    consulting_only: Optional[bool] = None,
):
    """Apply all common where-clause filters to a job query."""
    if status:
        q = q.where(Job.status == status)
    if portal:
        q = q.where(Job.source_portal == portal)
    if company:
        q = q.where(Job.company.ilike(f"%{company}%"))
    if has_hr_email is True:
        q = q.where(Job.hr_email.isnot(None))
    elif has_hr_email is False:
        q = q.where(Job.hr_email.is_(None))
    if min_score is not None:
        q = q.where(Job.relevance_score >= min_score)
    if max_score is not None:
        q = q.where(Job.relevance_score <= max_score)
    if search:
        t = f"%{search}%"
        q = q.where(
            or_(
                Job.job_title.ilike(t),
                Job.company.ilike(t),
                Job.location.ilike(t),
                Job.hr_email.ilike(t),
            )
        )
    if has_cover is True:
        q = q.where(Job.cover_letter.isnot(None))
    elif has_cover is False:
        q = q.where(Job.cover_letter.is_(None))
    if job_type:
        q = q.where(Job.job_type == job_type)
    if scraped_after:
        # scraped_at is a timestamp column — parse the ISO date string to a
        # datetime so SQLAlchemy binds it as a timestamp, not a varchar.
        try:
            scraped_after_dt = datetime.fromisoformat(scraped_after)
        except ValueError:
            scraped_after_dt = None
        if scraped_after_dt is not None:
            q = q.where(Job.scraped_at >= scraped_after_dt)
    if posted_after:
        try:
            posted_after_dt = datetime.fromisoformat(posted_after)
        except ValueError:
            posted_after_dt = None
        if posted_after_dt is not None:
            q = q.where(Job.posted_date >= posted_after_dt)

    # Filter out jobs with active sends (matches bulk send logic)
    if has_active_send is False:
        from services.api.models.db import SendLog
        _ACTIVE_STATUSES = ("queued", "sent", "deferred", "soft_bounced", "blocked",
                            "delivered", "opened", "clicked")
        q = q.where(
            ~exists(
                select(SendLog.id).where(
                    SendLog.job_id == Job.id,
                    SendLog.status.in_(_ACTIVE_STATUSES),
                )
            )
        )

    # mnc_only and consulting_only are mutually exclusive *positively* — a job
    # can't be both. Reject the impossible combination so callers learn instead
    # of silently getting an empty result set.
    if mnc_only is True and consulting_only is True:
        # Note: can't use `status.HTTP_422_*` here — the function parameter
        # `status` shadows the fastapi status module in this scope.
        raise HTTPException(
            status_code=422,
            detail="mnc_only=true and consulting_only=true cannot both be set "
                   "(a job has exactly one source_portal). Pick one.",
        )

    if mnc_only is True:
        q = q.where(Job.source_portal == "mnc_direct")
    elif mnc_only is False:
        q = q.where(Job.source_portal != "mnc_direct")

    if consulting_only is True:
        q = q.where(Job.source_portal == "consulting_direct")
    elif consulting_only is False:
        q = q.where(Job.source_portal != "consulting_direct")

    # Always exclude blacklisted companies — mirrors is_company_blacklisted() logic:
    # bidirectional case-insensitive substring match, with and without spaces.
    job_co_lower = func.lower(Job.company)
    job_co_nospace = func.lower(func.replace(Job.company, " ", ""))
    bl_lower = func.lower(BlacklistedCompany.name)
    bl_nospace = func.lower(func.replace(BlacklistedCompany.name, " ", ""))
    q = q.where(
        ~exists(
            select(BlacklistedCompany.id).where(
                or_(
                    job_co_lower.like(func.concat("%", bl_lower, "%")),
                    bl_lower.like(func.concat("%", job_co_lower, "%")),
                    job_co_nospace.like(func.concat("%", bl_nospace, "%")),
                    bl_nospace.like(func.concat("%", job_co_nospace, "%")),
                )
            )
        )
    )
    return q


@router.get("", response_model=list[JobOut])
async def list_jobs(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    # existing filters
    status: Optional[str] = Query(None),
    portal: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    has_hr_email: Optional[bool] = Query(None),
    min_score: Optional[float] = Query(None),
    # new filters
    search: Optional[str] = Query(None, description="Search title, company, location, hr_email"),
    max_score: Optional[float] = Query(None),
    has_cover: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(None),
    has_active_send: Optional[bool] = Query(None, description="Exclude jobs with active send attempts"),
    scraped_after: Optional[str] = Query(None, description="ISO date string, e.g. 2026-04-10"),
    posted_after: Optional[str] = Query(None, description="ISO date string, e.g. 2026-04-10"),
    mnc_only: Optional[bool] = Query(None, description="true=MNC jobs only, false=exclude MNC jobs"),
    consulting_only: Optional[bool] = Query(None, description="true=Consulting jobs only, false=exclude Consulting jobs"),
    # sorting
    sort_by: str = Query(default="scraped_at", pattern="^(scraped_at|relevance_score|company|job_title)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    # pagination
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    cache_key = _list_cache_key(
        status=status, portal=portal, company=company, has_hr_email=has_hr_email,
        min_score=min_score, search=search, max_score=max_score, has_cover=has_cover,
        job_type=job_type, has_active_send=has_active_send, scraped_after=scraped_after,
        posted_after=posted_after, mnc_only=mnc_only, consulting_only=consulting_only,
        sort_by=sort_by, sort_dir=sort_dir,
        page=page, page_size=page_size,
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return [JobOut(**j) for j in cached]

    q = select(Job)
    q = _apply_job_filters(
        q,
        status=status,
        portal=portal,
        company=company,
        has_hr_email=has_hr_email,
        min_score=min_score,
        search=search,
        max_score=max_score,
        has_cover=has_cover,
        job_type=job_type,
        has_active_send=has_active_send,
        scraped_after=scraped_after,
        posted_after=posted_after,
        mnc_only=mnc_only,
        consulting_only=consulting_only,
    )
    sort_col = {
        "scraped_at": Job.scraped_at,
        "relevance_score": Job.relevance_score,
        "company": Job.company,
        "job_title": Job.job_title,
    }[sort_by]
    q = q.order_by(asc(sort_col) if sort_dir == "asc" else desc(sort_col))
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    jobs = result.scalars().all()

    import asyncio
    asyncio.ensure_future(cache_set(cache_key, [JobOut.model_validate(j).model_dump(mode="json") for j in jobs], _JOBS_CACHE_TTL))
    return jobs


@router.get("/count")
async def count_jobs(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    portal: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    has_hr_email: Optional[bool] = Query(None),
    min_score: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    max_score: Optional[float] = Query(None),
    has_cover: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(None),
    has_active_send: Optional[bool] = Query(None, description="Exclude jobs with active send attempts"),
    scraped_after: Optional[str] = Query(None),
    posted_after: Optional[str] = Query(None),
    mnc_only: Optional[bool] = Query(None),
    consulting_only: Optional[bool] = Query(None),
) -> dict:
    cache_key = _count_cache_key(
        status=status, portal=portal, company=company, has_hr_email=has_hr_email,
        min_score=min_score, search=search, max_score=max_score, has_cover=has_cover,
        job_type=job_type, has_active_send=has_active_send, scraped_after=scraped_after,
        posted_after=posted_after, mnc_only=mnc_only, consulting_only=consulting_only,
    )
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    q = select(func.count()).select_from(Job)
    q = _apply_job_filters(
        q,
        status=status,
        portal=portal,
        company=company,
        has_hr_email=has_hr_email,
        min_score=min_score,
        search=search,
        max_score=max_score,
        has_cover=has_cover,
        job_type=job_type,
        has_active_send=has_active_send,
        scraped_after=scraped_after,
        posted_after=posted_after,
        mnc_only=mnc_only,
        consulting_only=consulting_only,
    )
    result = await db.execute(q)
    data = {"count": result.scalar_one()}

    import asyncio
    asyncio.ensure_future(cache_set(cache_key, data, _COUNT_CACHE_TTL))
    return data


@router.get("/ids", response_model=list[str])
async def list_job_ids(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    portal: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    has_hr_email: Optional[bool] = Query(None),
    min_score: Optional[float] = Query(None),
    search: Optional[str] = Query(None),
    max_score: Optional[float] = Query(None),
    has_cover: Optional[bool] = Query(None),
    job_type: Optional[str] = Query(None),
    has_active_send: Optional[bool] = Query(None),
    scraped_after: Optional[str] = Query(None),
    posted_after: Optional[str] = Query(None),
    mnc_only: Optional[bool] = Query(None),
    consulting_only: Optional[bool] = Query(None),
) -> list[str]:
    """Return all matching job IDs for the given filters (no pagination cap).

    Used by the frontend "Select All Matching" bulk action to get the full
    set of IDs without being limited by the page_size=100 cap on GET /jobs.
    Capped at 5000 results server-side for safety.
    """
    q = select(Job.id)
    q = _apply_job_filters(
        q,
        status=status,
        portal=portal,
        company=company,
        has_hr_email=has_hr_email,
        min_score=min_score,
        search=search,
        max_score=max_score,
        has_cover=has_cover,
        job_type=job_type,
        has_active_send=has_active_send,
        scraped_after=scraped_after,
        posted_after=posted_after,
        mnc_only=mnc_only,
        consulting_only=consulting_only,
    )
    q = q.limit(5000)
    result = await db.execute(q)
    return [str(row[0]) for row in result.all()]


@router.post("/trigger-mnc-scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_mnc_scrape(
    current_user: Auth,
    candidate_id: Optional[str] = None,
):
    """Enqueue an MNC scrape dispatcher task.

    The dispatcher acquires a per-tenant Redis lock; if a scrape is already
    in flight the response carries `status: "already_running"` and HTTP 409.
    """
    from services.api.core.cache import get_redis
    from services.scraper.celery_app import celery_app as _celery

    tid = current_user.tenant_id
    lock_key = f"mnc:scrape:lock:{tid}"

    # Cheap pre-check so the UI gets immediate feedback; the worker still
    # re-acquires atomically (NX EX) — that's the real source of truth.
    try:
        r = await get_redis()
        if r is not None and await r.exists(lock_key):
            raise HTTPException(
                status_code=409,
                detail={"status": "already_running", "tenant_id": tid},
            )
    except HTTPException:
        raise
    except Exception:
        pass  # Redis-down: fall through and let the worker decide.

    task = _celery.send_task(
        "services.scraper.tasks.mnc_scrape_dispatch_task",
        kwargs={"candidate_id": candidate_id, "tenant_id": tid},
        queue="jh_scraping_mnc_dispatch",
    )
    return {
        "task_id": task.id,
        "dispatch_id": task.id,
        "status": "queued",
        "portal": "mnc_direct",
    }


@router.get("/mnc-scrape-status")
async def get_mnc_scrape_status(current_user: Auth):
    """Return current MNC scrape progress for the caller's tenant.

    Reads the per-tenant Redis hash populated by `mnc_scrape_dispatch_task`
    and incremented by each `mnc_scrape_company_task`.
    """
    from services.api.core.cache import get_redis

    tid = current_user.tenant_id
    lock_key = f"mnc:scrape:lock:{tid}"
    progress_key = f"mnc:scrape:progress:{tid}"

    r = await get_redis()
    if r is None:
        return {"in_flight": False, "progress": None}

    try:
        in_flight = bool(await r.exists(lock_key))
        raw = await r.hgetall(progress_key) or {}
    except Exception:
        return {"in_flight": False, "progress": None}

    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    progress = {
        "dispatch_id": raw.get("dispatch_id"),
        "candidate_id": raw.get("candidate_id") or None,
        "total": _int(raw.get("total")),
        "done": _int(raw.get("done")),
        "saved": _int(raw.get("saved")),
        "started_at": raw.get("started_at"),
        "finished_at": raw.get("finished_at"),
        "final_saved": _int(raw.get("final_saved")) if raw.get("final_saved") else None,
        "final_errors": _int(raw.get("final_errors")) if raw.get("final_errors") else 0,
        "final_timeouts": _int(raw.get("final_timeouts")) if raw.get("final_timeouts") else 0,
    } if raw else None

    return {"in_flight": in_flight, "progress": progress}


@router.post("/trigger-consulting-scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_consulting_scrape(
    current_user: Auth,
    candidate_id: Optional[str] = None,
):
    """Enqueue a consulting/outsourcing scrape dispatcher task."""
    from services.api.core.cache import get_redis
    from services.scraper.celery_app import celery_app as _celery

    tid = current_user.tenant_id
    lock_key = f"consulting:scrape:lock:{tid}"

    try:
        r = await get_redis()
        if r is not None and await r.exists(lock_key):
            raise HTTPException(
                status_code=409,
                detail={"status": "already_running", "tenant_id": tid},
            )
    except HTTPException:
        raise
    except Exception:
        pass

    task = _celery.send_task(
        "services.scraper.tasks.consulting_scrape_dispatch_task",
        kwargs={"candidate_id": candidate_id, "tenant_id": tid},
        queue="jh_scraping_consulting_dispatch",
    )
    return {
        "task_id": task.id,
        "dispatch_id": task.id,
        "status": "queued",
        "portal": "consulting_direct",
    }


@router.get("/consulting-scrape-status")
async def get_consulting_scrape_status(current_user: Auth):
    """Return current consulting scrape progress for the caller's tenant."""
    from services.api.core.cache import get_redis

    tid = current_user.tenant_id
    lock_key = f"consulting:scrape:lock:{tid}"
    progress_key = f"consulting:scrape:progress:{tid}"

    r = await get_redis()
    if r is None:
        return {"in_flight": False, "progress": None}

    try:
        in_flight = bool(await r.exists(lock_key))
        raw = await r.hgetall(progress_key) or {}
    except Exception:
        return {"in_flight": False, "progress": None}

    def _int(v, default=0):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default

    progress = {
        "dispatch_id": raw.get("dispatch_id"),
        "candidate_id": raw.get("candidate_id") or None,
        "total": _int(raw.get("total")),
        "done": _int(raw.get("done")),
        "saved": _int(raw.get("saved")),
        "started_at": raw.get("started_at"),
        "finished_at": raw.get("finished_at"),
        "final_saved": _int(raw.get("final_saved")) if raw.get("final_saved") else None,
        "final_errors": _int(raw.get("final_errors")) if raw.get("final_errors") else 0,
        "final_timeouts": _int(raw.get("final_timeouts")) if raw.get("final_timeouts") else 0,
    } if raw else None

    return {"in_flight": in_flight, "progress": progress}


@router.post("/bulk_generate_cover")
async def bulk_generate_cover(
    body: BulkGenerateCoverRequest, _: Auth, db: AsyncSession = Depends(get_db)
):
    # Route through the rate-limited batch queue instead of firing N tasks
    # directly onto jh_cover_letter_generation. The batch queue drains at
    # GROQ_RPM/min so workers never stall competing for Groq slots.
    result = await db.execute(select(Job.id).where(Job.id.in_(body.job_ids)))
    found_ids = {row[0] for row in result.all()}
    not_found = [jid for jid in body.job_ids if jid not in found_ids]

    task_ids: list[str] = []
    for job_id in found_ids:
        task = celery_app.send_task(
            "services.ai.tasks.enqueue_cover_letter_task",
            args=[job_id, body.candidate_id],
            queue="jh_cover_letter_batch",
            ignore_result=True,
        )
        task_ids.append(task.id)

    return {"queued": len(task_ids), "not_found": not_found, "task_ids": task_ids}


@router.post("/bulk_send", response_model=BulkSendResponse)
async def bulk_send(
    body: BulkSendRequest, _: Auth, db: AsyncSession = Depends(get_db)
):
    from services.api.models.db import SendLog
    from services.sender.tasks import send_application_email_task

    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # Fetch all requested jobs in one IN query instead of N individual GETs
    jobs_result = await db.execute(
        select(Job.id, Job.hr_email, Job.cover_letter, Job.status).where(
            Job.id.in_(body.job_ids)
        )
    )
    jobs_map = {row.id: row for row in jobs_result.all()}

    # Block re-send if there is ANY active/in-flight send_log for this (job, candidate).
    # This covers: queued, sent, deferred (Brevo retrying), soft_bounced/blocked (our retry
    # scheduled), delivered/opened/clicked (already successful).
    # Only terminal failures (bounced, spam, unsubscribed) allow a fresh send attempt.
    _ACTIVE_STATUSES = ("queued", "sent", "deferred", "soft_bounced", "blocked",
                        "delivered", "opened", "clicked")
    already_active_result = await db.execute(
        select(SendLog.job_id).where(
            SendLog.job_id.in_(body.job_ids),
            SendLog.candidate_id == body.candidate_id,
            SendLog.status.in_(_ACTIVE_STATUSES),
        ).distinct()
    )
    already_active_by_candidate = {row[0] for row in already_active_result.all()}

    task_ids: list[str] = []
    skipped: list[SkippedJob] = []

    for job_id in body.job_ids:
        job = jobs_map.get(job_id)
        if not job:
            skipped.append(SkippedJob(job_id=job_id, reason="not_found"))
            continue
        if not job.hr_email:
            skipped.append(SkippedJob(job_id=job_id, reason="no_hr_email"))
            continue
        if not job.cover_letter and not body.dry_run:
            skipped.append(SkippedJob(job_id=job_id, reason="no_cover_letter"))
            continue
        # Block only if THIS candidate has an active send — not if a different candidate did.
        if job_id in already_active_by_candidate and not body.dry_run:
            skipped.append(SkippedJob(job_id=job_id, reason="already_sent"))
            continue

        if body.dry_run:
            task_ids.append(f"dry_run_{job_id}")
            continue

        task = celery_app.send_task(
            "services.sender.tasks.send_application_email_task",
            kwargs={
                "job_id": job_id,
                "candidate_id": body.candidate_id,
                "override_email": None,
                "override_subject": None,
                "attach_resume": body.attach_resume,
                "dry_run": False,
            },
            queue="jh_email_send",
            ignore_result=True,
        )
        task_ids.append(task.id)

    return BulkSendResponse(
        queued=len(task_ids),
        skipped=skipped,
        task_ids=task_ids,
        dry_run=body.dry_run,
    )


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, _: Auth, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.patch("/{job_id}/status", response_model=JobOut)
async def update_job_status(
    job_id: str, body: JobStatusUpdate, _: Auth, db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.status = body.status
    await db.flush()
    return job


@router.patch("/{job_id}/hr-email", response_model=JobOut)
async def set_job_hr_email(
    job_id: str, body: HrEmailUpdate, _: Auth, db: AsyncSession = Depends(get_db)
):
    """Manually set the HR email for a job, bypassing auto-discovery.

    Marks discovery_status as 'found' and resets the attempt counter so
    the job is no longer excluded from backfill runs.
    """
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    job.hr_email = body.hr_email.strip() or None
    if job.hr_email:
        job.hr_email_discovery_status = "found"
        job.hr_email_discovered_at = datetime.now(timezone.utc).replace(tzinfo=None)
        job.hr_email_discovery_attempts = 0
        from services.api.models.hr_email_utils import upsert_hr_email
        await upsert_hr_email(
            session=db,
            tenant_id=job.tenant_id,
            email=job.hr_email,
            increment_job_count=True,
        )
    else:
        # Clearing the email — reset to pending so backfill retries
        job.hr_email_discovery_status = "pending"
        job.hr_email_discovery_attempts = 0
        job.hr_email_discovered_at = None
    await db.commit()
    await db.refresh(job)
    return job


@router.post("/{job_id}/generate_cover")
async def generate_cover_letter(
    job_id: str, body: GenerateCoverRequest, _: Auth, db: AsyncSession = Depends(get_db)
):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    from services.ai.tasks import generate_cover_letter_task

    task = celery_app.send_task(
        "services.ai.tasks.generate_cover_letter_task",
        args=[job_id, body.candidate_id],
        kwargs={"tone": body.tone, "custom_instructions": body.custom_instructions},
        queue="jh_cover_letter_generation",
        ignore_result=True,
    )
    return {"message": "Cover letter generation queued", "celery_task_id": task.id, "job_id": job_id}


@router.get("/{job_id}/timeline", response_model=JobTimeline)
async def get_job_timeline(job_id: str, _: Auth, db: AsyncSession = Depends(get_db)):
    """Return the full application lifecycle timeline for a job.

    Assembles events from the Job row and its most recent SendLog.
    All timestamps are taken from existing DB columns — no new tables needed.
    """
    from services.api.models.db import SendLog

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Fetch the most recent send log for this job (latest sent_at)
    sl_result = await db.execute(
        select(SendLog)
        .where(SendLog.job_id == job_id)
        .order_by(desc(SendLog.sent_at))
        .limit(1)
    )
    send_log: SendLog | None = sl_result.scalar_one_or_none()

    events: list[TimelineEvent] = [
        TimelineEvent(
            event="scraped",
            label="Scraped",
            timestamp=job.scraped_at,
            done=job.scraped_at is not None,
            metadata={"portal": job.source_portal},
        ),
        TimelineEvent(
            event="scored",
            label="Scored",
            timestamp=job.scraped_at,  # scoring runs synchronously during scrape
            done=job.relevance_score is not None,
            metadata={"score": job.relevance_score},
        ),
        TimelineEvent(
            event="cover_generated",
            label="Cover Letter Generated",
            timestamp=job.cover_letter_generated_at,
            done=job.cover_letter_generated_at is not None,
        ),
        TimelineEvent(
            event="email_sent",
            label="Email Sent",
            timestamp=send_log.sent_at if send_log else None,
            done=send_log is not None and send_log.sent_at is not None,
            metadata={"to": send_log.to_email, "subject": send_log.subject} if send_log else None,
        ),
        TimelineEvent(
            event="delivered",
            label="Delivered",
            timestamp=send_log.delivered_at if send_log else None,
            done=send_log is not None and send_log.delivered_at is not None,
        ),
        TimelineEvent(
            event="opened",
            label="Opened",
            timestamp=send_log.opened_at if send_log else None,
            done=send_log is not None and send_log.opened_at is not None,
        ),
        TimelineEvent(
            event="clicked",
            label="Clicked",
            timestamp=send_log.clicked_at if send_log else None,
            done=send_log is not None and send_log.clicked_at is not None,
        ),
    ]

    return JobTimeline(job_id=job_id, events=events)
