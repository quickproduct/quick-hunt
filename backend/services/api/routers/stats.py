"""Stats router — dashboard aggregates."""
import asyncio
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, or_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_get, cache_set
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import BlacklistedCompany, Job, SendLog, User
from services.api.schemas.schemas import HREmailPipelineStats, StatsOut
from services.common.placeholder_emails import PLACEHOLDER_DOMAINS, PLACEHOLDER_EMAILS

router = APIRouter(tags=["stats"])
Auth = Annotated[User, Depends(get_current_user)]

_CACHE_TTL = 30  # seconds — matches frontend auto-refresh interval


@router.get("/stats", response_model=StatsOut)
async def get_stats(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
    candidate_id: Optional[str] = Query(None),
):
    # Per-tenant cache key — prevents tenant A from seeing tenant B's cached stats
    cache_key = f"stats:dashboard:{current_user.tenant_id}:{candidate_id or 'all'}"

    # ── 1. Cache hit — avoids any DB work for 30 s after first call ───────────
    cached = await cache_get(cache_key)
    if cached is not None:
        return StatsOut(**cached)

    # ── 2. Run all 6 queries on the shared session ────────────────────────────
    # Sequential on a single connection — uses one warm pool connection rather
    # than opening 6 new ones (which each require a TLS handshake to Neon).
    # With a warm pool this costs ~6 × 10–30 ms = 60–180 ms vs 6 × 300–500 ms
    # for 6 separate cold connections.  The 30 s Redis cache means this path
    # is hit at most once per 30 s anyway.

    # Build blacklist filter subquery once (mirrors jobs.py _apply_job_filters logic)
    # This ensures dashboard counts match job page counts
    job_co_lower = func.lower(Job.company)
    job_co_nospace = func.lower(func.replace(Job.company, " ", ""))
    bl_lower = func.lower(BlacklistedCompany.name)
    bl_nospace = func.lower(func.replace(BlacklistedCompany.name, " ", ""))

    blacklist_filter = ~exists(
        select(BlacklistedCompany.id).where(
            or_(
                job_co_lower.like(func.concat("%", bl_lower, "%")),
                bl_lower.like(func.concat("%", job_co_lower, "%")),
                job_co_nospace.like(func.concat("%", bl_nospace, "%")),
                bl_nospace.like(func.concat("%", job_co_nospace, "%")),
            )
        )
    )

    # Optional per-candidate filter for all job queries
    candidate_filters = [Job.candidate_id == candidate_id] if candidate_id else []

    total_result = await db.execute(
        select(func.count(Job.id)).where(blacklist_filter, *candidate_filters)
    )
    total_jobs = total_result.scalar() or 0

    status_result = await db.execute(
        select(Job.status, func.count(Job.id))
        .where(blacklist_filter, *candidate_filters)
        .group_by(Job.status)
    )
    jobs_by_status = {row[0]: row[1] for row in status_result.all()}

    portal_result = await db.execute(
        select(Job.source_portal, func.count(Job.id))
        .where(blacklist_filter, *candidate_filters)
        .group_by(Job.source_portal)
    )
    jobs_by_portal = {row[0]: row[1] for row in portal_result.all()}

    if candidate_id:
        email_q = (
            select(SendLog.status, func.count(SendLog.id))
            .join(Job, SendLog.job_id == Job.id)
            .where(Job.candidate_id == candidate_id)
            .group_by(SendLog.status)
        )
    else:
        email_q = (
            select(SendLog.status, func.count(SendLog.id))
            .group_by(SendLog.status)
        )
    email_result = await db.execute(email_q)
    email_by_status = {row[0]: row[1] for row in email_result.all()}

    cover_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.cover_letter.isnot(None))
        .where(blacklist_filter, *candidate_filters)
    )
    cover_letters = cover_result.scalar() or 0

    hr_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.hr_email.isnot(None))
        .where(blacklist_filter, *candidate_filters)
    )
    jobs_with_hr = hr_result.scalar() or 0

    # "Ready to send" = cover_generated status (not yet sent) + real HR email.
    # Uses exactly the same criteria as the jobs page "Ready to Apply" preset:
    # status=cover_generated + hr_email IS NOT NULL, then additionally excludes
    # Indeed placeholder domains that the jobs page shows as "Found" but are
    # not real HR contacts (they would fail at send time anyway).
    placeholder_domain_filters = [
        ~Job.hr_email.ilike(f"%@{d}") for d in PLACEHOLDER_DOMAINS
    ]
    placeholder_exact_filters = [
        Job.hr_email != email for email in PLACEHOLDER_EMAILS
    ]
    placeholder_image_filters = [
        ~Job.hr_email.ilike(f"%.{ext}") for ext in
        ("png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "css", "js")
    ]
    ready_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.status == "cover_generated")
        .where(Job.hr_email.isnot(None))
        .where(*placeholder_domain_filters)
        .where(*placeholder_exact_filters)
        .where(*placeholder_image_filters)
        .where(blacklist_filter, *candidate_filters)
    )
    jobs_ready = ready_result.scalar() or 0

    # Missing HR email = scraped/scored/cover_generated but hr_email is NULL
    missing_hr_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.hr_email.is_(None))
        .where(Job.status.notin_(["filtered", "sent", "bounced", "error"]))
        .where(blacklist_filter, *candidate_filters)
    )
    jobs_missing_hr = missing_hr_result.scalar() or 0

    # HR unreachable = discovery attempts exhausted
    unreachable_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.hr_email_discovery_status == "unreachable")
        .where(blacklist_filter, *candidate_filters)
    )
    jobs_hr_unreachable = unreachable_result.scalar() or 0

    # Pending approval = has cover + HR email but waiting on manual review
    pending_result = await db.execute(
        select(func.count(Job.id))
        .where(Job.status == "pending_approval")
        .where(blacklist_filter, *candidate_filters)
    )
    jobs_pending_approval = pending_result.scalar() or 0

    stats = StatsOut(
        total_jobs=total_jobs,
        jobs_by_status=jobs_by_status,
        jobs_by_portal=jobs_by_portal,
        emails_sent=(
            email_by_status.get("sent", 0)
            + email_by_status.get("delivered", 0)
            + email_by_status.get("opened", 0)
            + email_by_status.get("clicked", 0)
        ),
        emails_delivered=email_by_status.get("delivered", 0),
        emails_opened=email_by_status.get("opened", 0),
        emails_clicked=email_by_status.get("clicked", 0),
        emails_bounced=email_by_status.get("bounced", 0),
        emails_soft_bounced=email_by_status.get("soft_bounced", 0),
        cover_letters_generated=cover_letters,
        jobs_with_hr_email=jobs_with_hr,
        jobs_ready=jobs_ready,
        jobs_missing_hr=jobs_missing_hr,
        jobs_pending_approval=jobs_pending_approval,
        jobs_hr_unreachable=jobs_hr_unreachable,
    )

    # ── 3. Populate cache — fire-and-forget so it never blocks the response ───
    asyncio.ensure_future(cache_set(cache_key, stats.model_dump(), _CACHE_TTL))

    return stats


@router.get("/stats/hr-email-pipeline", response_model=HREmailPipelineStats)
async def get_hr_email_pipeline_stats(
    current_user: Auth,
    db: AsyncSession = Depends(get_db),
):
    """HR email pipeline health — detailed breakdown of discovery status.

    Returns counts by discovery status, portal-level breakdown for the
    cover-ready bottleneck, and circuit breaker state from Redis.
    """
    # Discovery status counts
    status_result = await db.execute(
        select(Job.hr_email_discovery_status, func.count(Job.id))
        .where(Job.status.notin_(["filtered"]))
        .group_by(Job.hr_email_discovery_status)
    )
    discovery_status_counts = {row[0] or "pending": row[1] for row in status_result.all()}

    # Cover-ready bottleneck
    cover_missing = await db.execute(
        select(func.count(Job.id))
        .where(Job.status == "cover_generated")
        .where(Job.hr_email.is_(None))
    )
    cover_ready_missing_hr = cover_missing.scalar() or 0

    cover_with = await db.execute(
        select(func.count(Job.id))
        .where(Job.status == "cover_generated")
        .where(Job.hr_email.isnot(None))
    )
    cover_ready_with_hr = cover_with.scalar() or 0

    # Portal breakdown for cover_ready missing HR
    portal_result = await db.execute(
        select(Job.source_portal, func.count(Job.id))
        .where(Job.status == "cover_generated")
        .where(Job.hr_email.is_(None))
        .group_by(Job.source_portal)
        .order_by(func.count(Job.id).desc())
        .limit(15)
    )
    missing_hr_by_portal = {row[0]: row[1] for row in portal_result.all()}

    # Circuit breaker state from Redis
    circuit_breakers: dict[str, str] = {}
    try:
        from services.api.core.config import get_settings
        import redis as sync_redis

        settings = get_settings()
        r = sync_redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )
        for task_name in [
            "cover_ready_hr_fetch_task",
            "backfill_hr_emails_task",
            "fix_placeholder_emails_task",
        ]:
            state = r.get(f"cron:circuit:{task_name}:state") or "closed"
            circuit_breakers[task_name] = state
        r.close()
    except Exception:
        circuit_breakers = {"error": "redis_unavailable"}

    return HREmailPipelineStats(
        jobs_pending_discovery=discovery_status_counts.get("pending", 0)
        + discovery_status_counts.get("not_found", 0),
        jobs_unreachable=discovery_status_counts.get("unreachable", 0),
        jobs_found=discovery_status_counts.get("found", 0),
        cover_ready_missing_hr=cover_ready_missing_hr,
        cover_ready_with_hr=cover_ready_with_hr,
        discovery_status_counts=discovery_status_counts,
        missing_hr_by_portal=missing_hr_by_portal,
        circuit_breakers=circuit_breakers,
    )
