"""Admin router — system health, worker control, feature flags, logs, queue monitoring.

All endpoints require owner or admin role (AdminPlus dependency).
"""
from typing import Annotated, Any, AsyncGenerator, Literal, Optional
import asyncio
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.database import get_db
from services.api.core.dependencies import AdminPlus
from services.api.models.db import User
from services.api.services.admin_service import (
    ALL_PORTALS,
    apply_performance_mode,
    check_system_health,
    detect_dead_workers,
    get_cover_letter_status,
    get_current_performance_mode,
    get_docker_status,
    get_features,
    get_log_summary,
    get_portals,
    get_queue_stats,
    get_recent_events,
    get_worker_config,
    get_workers_live_status,
    is_autoscale_enabled,
    pause_worker,
    read_log_file,
    release_config_lock,
    restart_workers,
    resume_worker,
    rollback_config,
    run_autoscale_check,
    acquire_config_lock,
    send_docker_command,
    set_autoscale_enabled,
    snapshot_config,
    start_events_consumer,
    toggle_portal,
    update_features,
    update_worker_scale,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])
Auth = Annotated[User, Depends(AdminPlus)]


# ── Request schemas ──────────────────────────────────────────────────────────

class FeatureUpdateRequest(BaseModel):
    auto_send_enabled: bool | None = None
    langchain_enabled: bool | None = None
    semantic_filter_enabled: bool | None = None
    score_threshold: int | None = None


class ScrapeFilterConfigRequest(BaseModel):
    max_job_age_days: int | None = None
    strict_date_mode: bool | None = None


class WorkerScaleRequest(BaseModel):
    worker: str
    scale: int | None = None
    concurrency: int | None = None


class PerformanceModeRequest(BaseModel):
    mode: Literal["turbo", "normal", "economy"]


# ── System Health ────────────────────────────────────────────────────────────

@router.get("/system/health")
async def system_health(_: Auth):
    """Check connectivity to DB, RabbitMQ, Redis, Ollama."""
    return await check_system_health()


# ── Queue Monitoring ─────────────────────────────────────────────────────────

@router.get("/queues")
async def queue_status(_: Auth):
    """RabbitMQ queue depths and consumer counts for all jh_* queues."""
    return await get_queue_stats()


# ── Log Viewer ───────────────────────────────────────────────────────────────

@router.get("/logs/{level}")
async def get_logs(
    _: Auth,
    level: Literal["critical", "error", "warning", "app"],
    lines: int = Query(default=100, ge=1, le=500),
):
    """Read last N lines from a log file."""
    return read_log_file(level, lines)


@router.get("/logs-summary")
async def logs_summary(_: Auth):
    """Line counts for each log file + app.log size."""
    return get_log_summary()


# ── Feature Flags ────────────────────────────────────────────────────────────

@router.get("/features")
async def features_get(_: Auth):
    """Get runtime feature flags (Redis overrides or config defaults)."""
    return await get_features()


@router.put("/features")
async def features_update(_: Auth, body: FeatureUpdateRequest):
    """Update runtime feature flags — takes effect immediately without restart."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No features to update")
    return await update_features(updates)


# ── Scrape Filter Config ──────────────────────────────────────────────────────

@router.get("/scrape-filter")
async def scrape_filter_get(_: Auth):
    """Get current scrape date filter settings."""
    from services.api.core.config import get_settings
    from services.api.core.cache import cache_get, cache_set

    settings = get_settings()
    override = await cache_get("admin:scrape_filter")
    if override:
        return override

    config = {
        "max_job_age_days": settings.max_job_age_days,
        "strict_date_mode": settings.scrape_strict_date_mode,
    }
    return config


@router.put("/scrape-filter")
async def scrape_filter_update(_: Auth, body: ScrapeFilterConfigRequest):
    """Update scrape date filter settings (stored in Redis for runtime override)."""
    from services.api.core.cache import cache_set
    from services.api.core.config import get_settings

    settings = get_settings()
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No settings to update")

    hard_cap = getattr(settings, "max_job_age_days_hard_cap", 90)
    requested_days = updates.get("max_job_age_days", settings.max_job_age_days)
    if requested_days < 1 or requested_days > hard_cap:
        raise HTTPException(
            status_code=400,
            detail=f"max_job_age_days must be between 1 and {hard_cap} (3-month hard cap)",
        )

    config = {
        "max_job_age_days": requested_days,
        "strict_date_mode": updates.get("strict_date_mode", settings.scrape_strict_date_mode),
    }

    await cache_set("admin:scrape_filter", config, ttl_seconds=None)  # persist indefinitely

    logger.info("admin_scrape_filter_updated", **config)
    return {"updated": True, **config}


# ── Portal Control ───────────────────────────────────────────────────────────

@router.get("/portals")
async def portals_get(_: Auth):
    """Get all portals with enabled/disabled status."""
    return await get_portals()


@router.put("/portals/{portal}/toggle")
async def portal_toggle(_: Auth, portal: str, enabled: bool = Query(...)):
    """Enable or disable a specific portal. Takes effect on next scrape dispatch."""
    try:
        return await toggle_portal(portal, enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ── Worker Config ────────────────────────────────────────────────────────────

@router.get("/workers/config")
async def workers_config_get(_: Auth):
    """Read current worker.config.yml."""
    cfg = get_worker_config()
    if "error" in cfg and "workers" not in cfg:
        raise HTTPException(status_code=500, detail=cfg["error"])
    return cfg


@router.put("/workers/scale")
async def workers_scale(_: Auth, body: WorkerScaleRequest):
    """Update scale/concurrency for a specific worker. Triggers restart."""
    locked = await acquire_config_lock("admin-scale")
    if not locked:
        raise HTTPException(status_code=409, detail="Config is being modified by another admin. Try again in 30s.")
    try:
        await snapshot_config()
        return update_worker_scale(body.worker, body.scale, body.concurrency)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await release_config_lock()


@router.post("/workers/performance-mode")
async def workers_performance_mode(_: Auth, body: PerformanceModeRequest):
    """Apply a performance preset (turbo/normal/economy) to all workers."""
    locked = await acquire_config_lock("admin")
    if not locked:
        raise HTTPException(status_code=409, detail="Config is being modified by another admin. Try again in 30s.")
    try:
        await snapshot_config()
        result = apply_performance_mode(body.mode)
        return result
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        await release_config_lock()


@router.get("/workers/performance-mode")
async def workers_get_performance_mode(_: Auth):
    """Detect and return the currently active performance mode."""
    return get_current_performance_mode()


@router.post("/workers/rollback")
async def workers_rollback(_: Auth):
    """Rollback to the previous worker configuration snapshot."""
    locked = await acquire_config_lock("admin-rollback")
    if not locked:
        raise HTTPException(status_code=409, detail="Config is being modified. Try again.")
    try:
        return await rollback_config()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        await release_config_lock()


@router.get("/workers/live-status")
async def workers_live_status(_: Auth):
    """Real-time status of all Celery workers via inspect API."""
    return await get_workers_live_status()


class RestartRequest(BaseModel):
    service: str | None = None


@router.post("/workers/restart")
async def workers_restart(_: Auth, body: RestartRequest = None):
    """Restart worker pool(s) — in-flight tasks complete first, then pool restarts."""
    service = body.service if body else None
    return await restart_workers(service)


class PauseResumeRequest(BaseModel):
    service: str


@router.post("/workers/pause")
async def workers_pause(_: Auth, body: PauseResumeRequest):
    """Pause a worker — stops consuming from its queues. In-flight tasks complete normally."""
    return await pause_worker(body.service)


@router.post("/workers/resume")
async def workers_resume(_: Auth, body: PauseResumeRequest):
    """Resume a paused worker — starts consuming from its queues again."""
    return await resume_worker(body.service)


# ── Docker Agent ─────────────────────────────────────────────────────────────

class DockerCommandRequest(BaseModel):
    action: str
    params: dict = {}


@router.post("/docker/command")
async def docker_command(_: Auth, body: DockerCommandRequest):
    """Send a command to the Docker agent sidecar (scale, restart, restart_workers)."""
    return await send_docker_command(body.action, body.params, timeout=30.0)


@router.get("/docker/status")
async def docker_status(_: Auth):
    """Get current container status from the Docker agent."""
    return await get_docker_status()


# ── Auto-Scaler ──────────────────────────────────────────────────────────────

class AutoscaleToggleRequest(BaseModel):
    enabled: bool


@router.get("/autoscale/status")
async def autoscale_status(_: Auth):
    """Get auto-scaler status and recent decisions."""
    enabled = await is_autoscale_enabled()
    return {"enabled": enabled}


@router.post("/autoscale/toggle")
async def autoscale_toggle(_: Auth, body: AutoscaleToggleRequest):
    """Enable or disable the auto-scaler."""
    ok = await set_autoscale_enabled(body.enabled)
    return {"enabled": body.enabled, "updated": ok}


@router.post("/autoscale/check")
async def autoscale_check(_: Auth):
    """Trigger an immediate auto-scale check."""
    return await run_autoscale_check()


# ── Worker Events + Dead Worker Detection ────────────────────────────────────

@router.get("/workers/events")
async def workers_events(_: Auth, limit: int = Query(default=50, ge=1, le=200)):
    """Get recent Celery worker/task events from Redis."""
    events = await get_recent_events(limit)
    return {"events": events, "count": len(events)}


@router.get("/workers/dead")
async def workers_dead(_: Auth):
    """Detect workers that have stopped sending heartbeats."""
    dead = await detect_dead_workers()
    return {"dead_workers": dead, "count": len(dead)}


@router.get("/workers/events-stream")
async def workers_events_stream(request: Request, _: Auth):
    """SSE stream of live worker status (polls every 5s)."""
    async def event_generator() -> AsyncGenerator[str, None]:
        while True:
            if await request.is_disconnected():
                break
            payload: dict[str, Any] = {}
            try:
                status = await get_workers_live_status()
                payload["live_status"] = {
                    "services": status.get("services", {}),
                    "worker_count": len(status.get("workers", {})),
                }
            except Exception:
                payload["live_status"] = {"error": "unavailable"}

            try:
                dead = await detect_dead_workers()
                if dead:
                    payload["dead_workers"] = dead
            except Exception:
                pass

            try:
                events = await get_recent_events(10)
                if events:
                    payload["recent_events"] = events
            except Exception:
                pass

            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Cover Letter Status ───────────────────────────────────────────────────────

@router.get("/cover-letter-status")
async def cover_letter_status(_: Auth):
    """Get real-time cover letter freshness status across all jobs.

    Returns:
    - total_jobs: Total non-terminal jobs checked
    - fresh_covers: Jobs with covers generated after last candidate update
    - stale_covers: Jobs with covers generated before last candidate update (need refresh)
    - missing_covers: Jobs with no cover letter
    - stale_percentage: Percentage of stale covers
    - by_candidate: Per-candidate breakdown
    """
    return await get_cover_letter_status()


# ── Operator action registry / previews ──────────────────────────────────────

PHP_JOB_TERMS = (
    "php", "laravel", "codeigniter", "symfony", "lumen", "yii", "zend",
    "phalcon", "cakephp", "eloquent", "php artisan", "blade template",
    "wordpress", "woocommerce", "magento", "drupal",
)

ACTIVE_CLEANUP_STATUSES = ("sent", "bounced", "error")

ACTION_REGISTRY: dict[str, dict[str, Any]] = {
    "deduplicate": {
        "description": "Remove duplicate job listings from the database",
        "task": "services.scraper.tasks.deduplicate_jobs_task",
        "queue": "jh_jobs_maintenance",
        "destructive": True,
        "cleanup_kind": "duplicate",
    },
    "reset-email-discovery": {
        "description": "Reset unreachable HR email discovery jobs to pending",
        "task": None,
        "queue": None,
        "destructive": False,
    },
    "fill-missing-covers": {
        "description": "Generate cover letters for jobs without one",
        "task": "services.ai.tasks.fill_missing_covers_task",
        "queue": "jh_cover_letter_bulk",
        "destructive": False,
    },
    "backfill-hr-emails": {
        "description": "Run HR email discovery for jobs missing contact email",
        "task": "services.scraper.tasks.backfill_hr_emails_task",
        "queue": "jh_scraping_enrichment",
        "destructive": False,
    },
    "refresh-cover-letters": {
        "description": "Regenerate stale cover letters",
        "task": "services.ai.tasks.refresh_cover_letters_task",
        "queue": "jh_cover_letter_bulk",
        "destructive": False,
    },
    "cleanup-old-jobs": {
        "description": "Delete terminal jobs older than retention",
        "task": "services.scraper.tasks.cleanup_old_jobs_task",
        "queue": "jh_jobs_maintenance",
        "destructive": True,
        "cleanup_kind": "old_terminal",
    },
    "fix-placeholder-emails": {
        "description": "Replace placeholder/junk HR emails",
        "task": "services.scraper.tasks.fix_placeholder_emails_task",
        "queue": "jh_scraping_enrichment",
        "destructive": False,
    },
    "check-cover-letter-status": {
        "description": "Check cover letter freshness",
        "task": "services.ai.tasks.check_cover_letter_status_task",
        "queue": "jh_cover_letter_bulk",
        "destructive": False,
    },
    "pipeline-health-check": {
        "description": "Run full pipeline health diagnostic",
        "task": "services.scraper.tasks.pipeline_health_check_task",
        "queue": "jh_jobs_maintenance",
        "destructive": False,
    },
    "stale-lock-reaper": {
        "description": "Release expired singleton locks",
        "task": "services.scraper.tasks.stale_lock_reaper_task",
        "queue": "jh_jobs_maintenance",
        "destructive": False,
    },
    "purge-old-dated-jobs": {
        "description": "Delete old dated new/filtered jobs",
        "task": "services.scraper.tasks.purge_old_dated_jobs_task",
        "queue": "jh_jobs_maintenance",
        "destructive": True,
    },
    "non-php-cleanup": {
        "description": "Mark non-PHP jobs filtered",
        "task": None,
        "queue": None,
        "destructive": True,
        "cleanup_kind": "non_php",
    },
    "priority-cover-emailed": {
        "description": "Generate covers for high-priority emailed jobs first",
        "task": None,
        "queue": "jh_cover_letter_bulk",
        "destructive": False,
    },
    "current-month-pipeline": {
        "description": "Run HR discovery and missing covers for current-month jobs",
        "task": None,
        "queue": None,
        "destructive": False,
    },
    "generate-non-php-candidates": {
        "description": "Assign candidate + static cover letter to all non-PHP jobs",
        "task": None,
        "queue": None,
        "destructive": False,
    },
}


class ActionRunRequest(BaseModel):
    confirm: bool = False
    limit: int = 200


def _job_sample(row: Any, reason: str) -> dict[str, Any]:
    return {
        "id": row.id,
        "job_title": row.job_title,
        "company": row.company,
        "status": row.status,
        "source_portal": row.source_portal,
        "relevance_score": row.relevance_score,
        "reason": reason,
    }


def _php_match_expr(Job):
    from sqlalchemy import func as sa_func, or_

    haystack = sa_func.lower(
        sa_func.coalesce(Job.job_title, "")
        + " "
        + sa_func.coalesce(Job.job_description, "")
    )
    return or_(*[haystack.like(f"%{term}%") for term in PHP_JOB_TERMS])


async def _status_breakdown(db: AsyncSession) -> dict[str, int]:
    from sqlalchemy import func as sa_func
    from services.api.models.db import Job

    rows = await db.execute(select(Job.status, sa_func.count(Job.id)).group_by(Job.status))
    return {status or "unknown": count for status, count in rows.all()}


async def _preview_cleanup(kind: str, db: AsyncSession, limit: int = 20) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import and_, func as sa_func, not_, or_, text
    from services.api.models.db import Job

    limit = max(1, min(limit, 100))
    warnings: list[str] = []
    criteria: dict[str, Any] = {"kind": kind}

    if kind == "non_php":
        condition = and_(
            not_(_php_match_expr(Job)),
            Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
        )
        q_count = select(sa_func.count(Job.id)).where(condition)
        q_sample = (
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(desc(Job.scraped_at))
            .limit(limit)
        )
        reason = "No PHP/Laravel/framework keyword found in title or description"
        criteria.update({"php_terms": PHP_JOB_TERMS, "excluded_statuses": ACTIVE_CLEANUP_STATUSES})
        recommended = "Run ignore_non_php_jobs(confirm=True) to mark these jobs filtered."
    elif kind == "low_score":
        threshold = 40
        condition = and_(
            Job.relevance_score.isnot(None),
            Job.relevance_score < threshold,
            Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
        )
        q_count = select(sa_func.count(Job.id)).where(condition)
        q_sample = (
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(Job.relevance_score.asc(), desc(Job.scraped_at))
            .limit(limit)
        )
        reason = f"Relevance score below {threshold}"
        criteria.update({"relevance_score_lt": threshold, "excluded_statuses": ACTIVE_CLEANUP_STATUSES})
        recommended = "Review samples, then bulk mark filtered if they are genuinely irrelevant."
    elif kind == "missing_hr_email_stale":
        stale_before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
        condition = and_(
            Job.hr_email.is_(None),
            Job.scraped_at < stale_before,
            Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
        )
        q_count = select(sa_func.count(Job.id)).where(condition)
        q_sample = (
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(Job.scraped_at.asc())
            .limit(limit)
        )
        reason = "Missing HR email for more than 7 days"
        criteria.update({"hr_email": "missing", "scraped_before": stale_before.isoformat()})
        recommended = "Run backfill-hr-emails before ignoring these jobs."
    elif kind == "old_terminal":
        stale_before = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
        terminal = ("sent", "bounced", "error")
        condition = and_(Job.status.in_(terminal), Job.scraped_at < stale_before)
        q_count = select(sa_func.count(Job.id)).where(condition)
        q_sample = (
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(Job.scraped_at.asc())
            .limit(limit)
        )
        reason = "Terminal job older than 30 days"
        criteria.update({"terminal_statuses": terminal, "scraped_before": stale_before.isoformat()})
        warnings.append("cleanup-old-jobs deletes rows and embeddings.")
        recommended = "Run cleanup-old-jobs only after reviewing samples."
    elif kind == "duplicate":
        duplicate_sql = text("""
            WITH ranked AS (
                SELECT id, job_title, company, status, source_portal, relevance_score,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id, LOWER(TRIM(company))
                           ORDER BY
                               CASE status
                                   WHEN 'sent' THEN 0
                                   WHEN 'pending_approval' THEN 1
                                   WHEN 'cover_generated' THEN 2
                                   WHEN 'scoring' THEN 3
                                   WHEN 'new' THEN 4
                                   WHEN 'filtered' THEN 5
                                   ELSE 6
                               END,
                               scraped_at DESC
                       ) AS rn
                FROM jobs
            )
            SELECT id, job_title, company, status, source_portal, relevance_score
            FROM ranked
            WHERE rn > 1
            LIMIT :limit
        """)
        count_sql = text("""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY tenant_id, LOWER(TRIM(company)) ORDER BY scraped_at DESC
                ) AS rn
                FROM jobs
            )
            SELECT COUNT(*) FROM ranked WHERE rn > 1
        """)
        total = (await db.execute(count_sql)).scalar() or 0
        rows = (await db.execute(duplicate_sql, {"limit": limit})).all()
        return {
            "action": "preview_job_cleanup",
            "destructive": True,
            "would_affect_count": total,
            "criteria": {"kind": kind, "grouping": ["tenant_id", "lower(trim(company))"]},
            "samples": [_job_sample(r, "Duplicate company within tenant") for r in rows],
            "warnings": ["deduplicate deletes duplicate jobs plus related send_logs and embeddings."],
            "current_status_breakdown": await _status_breakdown(db),
            "recommended_confirmation": "Run deduplicate with confirm=True after reviewing samples.",
        }
    else:
        raise HTTPException(status_code=400, detail="Invalid cleanup kind")

    total = (await db.execute(q_count)).scalar() or 0
    rows = (await db.execute(q_sample)).all()
    return {
        "action": "preview_job_cleanup",
        "destructive": kind in {"duplicate", "old_terminal"},
        "would_affect_count": total,
        "criteria": criteria,
        "samples": [_job_sample(r, reason) for r in rows],
        "warnings": warnings,
        "current_status_breakdown": await _status_breakdown(db),
        "recommended_confirmation": recommended,
    }


# ── Quick Actions ────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}")
async def get_task_status(_: Auth, task_id: str, db: AsyncSession = Depends(get_db)):
    """Return Celery task state plus any matching CronRun and worker events."""
    from celery.result import AsyncResult
    from services.api.models.db import CronRun
    from services.scraper.celery_app import celery_app

    task = AsyncResult(task_id, app=celery_app)
    payload: dict[str, Any] = {
        "task_id": task_id,
        "state": task.state,
        "ready": task.ready(),
        "successful": task.successful() if task.ready() else False,
        "failed": task.failed(),
        "result": None,
        "error": None,
        "traceback": None,
        "cron_run": None,
        "recent_events": [],
    }
    if task.ready():
        if task.failed():
            payload["error"] = str(task.result)
            payload["traceback"] = task.traceback
        else:
            payload["result"] = task.result

    run_result = await db.execute(
        select(CronRun)
        .where(CronRun.celery_task_id == task_id)
        .order_by(desc(CronRun.started_at))
        .limit(1)
    )
    run = run_result.scalar_one_or_none()
    if run:
        payload["cron_run"] = {
            "id": run.id,
            "task_name": run.task_name,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "ended_at": run.ended_at.isoformat() if run.ended_at else None,
            "duration_ms": run.duration_ms,
            "status": run.status,
            "error_summary": run.error_summary,
            "post_state": run.post_state,
            "triggered_by": run.triggered_by,
            "worker_host": run.worker_host,
        }

    try:
        events = await get_recent_events(limit=100)
        payload["recent_events"] = [
            ev for ev in events
            if str(ev.get("task_id") or ev.get("uuid") or "") == task_id
        ][:10]
    except Exception as exc:
        payload["recent_events_error"] = str(exc)[:200]

    return payload


@router.post("/actions/{action}/preview")
async def preview_action(
    _: Auth,
    action: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
):
    """Preview the rows a maintenance action would affect without mutating data."""
    action = action.strip().lower()
    meta = ACTION_REGISTRY.get(action)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Unknown action: {action}")

    cleanup_kind = meta.get("cleanup_kind")
    if cleanup_kind:
        preview = await _preview_cleanup(cleanup_kind, db, limit)
        preview["action"] = action
        preview["description"] = meta["description"]
        preview["queue"] = meta.get("queue")
        preview["destructive"] = meta["destructive"]
        return preview

    if action == "fix-placeholder-emails":
        from sqlalchemy import or_, func as sa_func
        from services.api.models.db import Job
        from services.common.placeholder_emails import PLACEHOLDER_DOMAINS, PLACEHOLDER_EMAILS

        filters = [Job.hr_email.ilike(f"%@{domain}") for domain in PLACEHOLDER_DOMAINS]
        filters += [Job.hr_email == email for email in PLACEHOLDER_EMAILS]
        filters += [Job.hr_email.ilike(f"%.{ext}") for ext in ("png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "css", "js")]
        condition = or_(*filters)
        total = (await db.execute(select(sa_func.count(Job.id)).where(condition))).scalar() or 0
        rows = (await db.execute(
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(desc(Job.scraped_at))
            .limit(limit)
        )).all()
        return {
            "action": action,
            "description": meta["description"],
            "destructive": False,
            "would_affect_count": total,
            "criteria": {"hr_email": "placeholder_or_junk"},
            "samples": [_job_sample(r, "HR email looks like a placeholder or invalid file/domain") for r in rows],
            "warnings": [],
            "current_status_breakdown": await _status_breakdown(db),
            "recommended_confirmation": "Run fix-placeholder-emails to repair or clear these emails.",
        }

    if action == "backfill-hr-emails":
        from sqlalchemy import func as sa_func, or_
        from services.api.models.db import Job

        condition = (
            Job.hr_email.is_(None)
            & Job.status.notin_(ACTIVE_CLEANUP_STATUSES)
            & or_(Job.hr_email_discovery_attempts.is_(None), Job.hr_email_discovery_attempts < 3)
        )
        total = (await db.execute(select(sa_func.count(Job.id)).where(condition))).scalar() or 0
        rows = (await db.execute(
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(desc(Job.scraped_at))
            .limit(limit)
        )).all()
        return {
            "action": action,
            "description": meta["description"],
            "destructive": False,
            "would_affect_count": total,
            "criteria": {"hr_email": "missing", "excluded_statuses": ACTIVE_CLEANUP_STATUSES},
            "samples": [_job_sample(r, "Missing HR email and still eligible for discovery") for r in rows],
            "warnings": [],
            "current_status_breakdown": await _status_breakdown(db),
            "recommended_confirmation": "Run backfill-hr-emails to discover contacts.",
        }

    if action == "reset-email-discovery":
        from sqlalchemy import func as sa_func
        from services.api.models.db import Job

        condition = Job.hr_email.is_(None) & (Job.hr_email_discovery_status == "unreachable")
        total = (await db.execute(select(sa_func.count(Job.id)).where(condition))).scalar() or 0
        rows = (await db.execute(
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(desc(Job.scraped_at))
            .limit(limit)
        )).all()
        return {
            "action": action,
            "description": meta["description"],
            "destructive": False,
            "would_affect_count": total,
            "criteria": {"hr_email": "missing", "hr_email_discovery_status": "unreachable"},
            "samples": [_job_sample(r, "Unreachable HR discovery can be reset to pending") for r in rows],
            "warnings": [],
            "current_status_breakdown": await _status_breakdown(db),
            "recommended_confirmation": "Run reset-email-discovery to retry discovery.",
        }

    if action == "generate-non-php-candidates":
        from sqlalchemy import func as sa_func, and_, not_
        from services.api.models.db import Candidate, Job

        active_candidates = (await db.execute(
            select(Candidate).where(Candidate.is_active == True).limit(10)
        )).scalars().all()
        candidate_info = None
        if active_candidates:
            c = active_candidates[0]
            candidate_info = {
                "id": c.id,
                "name": c.name,
                "has_static_cover_letter": bool(c.static_cover_letter),
                "has_cover_letter_template": bool(c.cover_letter_template),
            }

        condition = and_(
            not_(_php_match_expr(Job)),
            Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
            Job.status != "filtered",
        )
        total = (await db.execute(select(sa_func.count(Job.id)).where(condition))).scalar() or 0
        rows = (await db.execute(
            select(Job.id, Job.job_title, Job.company, Job.status, Job.source_portal, Job.relevance_score)
            .where(condition)
            .order_by(desc(Job.scraped_at))
            .limit(limit)
        )).all()
        return {
            "action": action,
            "description": meta["description"],
            "destructive": False,
            "would_affect_count": total,
            "criteria": {"non_php_keywords": PHP_JOB_TERMS, "excluded_statuses": list(ACTIVE_CLEANUP_STATUSES) + ["filtered"]},
            "candidate": candidate_info,
            "samples": [_job_sample(r, "Non-PHP job — will be assigned candidate + static cover letter") for r in rows],
            "warnings": [],
            "current_status_breakdown": await _status_breakdown(db),
            "recommended_confirmation": "Run generate-non-php-candidates to assign candidate + static cover letter to all non-PHP jobs.",
        }

    return {
        "action": action,
        "description": meta["description"],
        "destructive": meta["destructive"],
        "would_affect_count": None,
        "criteria": {"preview": "No row-level preview available for this action"},
        "samples": [],
        "warnings": [],
        "current_status_breakdown": await _status_breakdown(db),
        "recommended_confirmation": "Run the action if this operational task is needed.",
    }


@router.get("/jobs/cleanup/preview/{kind}")
async def preview_job_cleanup(
    _: Auth,
    kind: str,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
):
    return await _preview_cleanup(kind.strip().lower(), db, limit)


@router.get("/actions/recommendations")
async def action_recommendations(_: Auth, db: AsyncSession = Depends(get_db)):
    """Return a short ranked list of useful safe maintenance actions."""
    candidates = [
        ("deduplicate", "duplicate", "Remove duplicate jobs"),
        ("backfill-hr-emails", "missing_hr_email_stale", "Backfill missing HR emails"),
        ("cleanup-old-jobs", "old_terminal", "Clean old terminal jobs"),
    ]
    items = []
    for action, kind, label in candidates:
        preview = await _preview_cleanup(kind, db, limit=5)
        count = preview.get("would_affect_count") or 0
        if count:
            items.append({
                "action": action,
                "label": label,
                "would_affect_count": count,
                "destructive": ACTION_REGISTRY.get(action, {}).get("destructive", False),
                "recommended_next_step": preview.get("recommended_confirmation"),
                "samples": preview.get("samples", []),
            })
    items.sort(key=lambda i: i["would_affect_count"], reverse=True)
    return {"recommendations": items[:5]}


@router.get("/pipeline/doctor")
async def pipeline_doctor(_: Auth, db: AsyncSession = Depends(get_db)):
    """Compact operator health report with recommended next actions."""
    async def _maybe(label: str, fn):
        try:
            return await fn()
        except Exception as exc:
            return {"error": f"{label} unavailable: {str(exc)[:200]}"}

    recommendations = await action_recommendations(_, db)
    return {
        "system_health": await _maybe("system health", check_system_health),
        "queue_depths": await _maybe("queue depths", get_queue_stats),
        "worker_live_status": await _maybe("worker live status", get_workers_live_status),
        "cron_kpis": await cron_kpis(_, db),
        "db_tables": await db_tables(_, db),
        "redis_health": await redis_health(_),
        "recommendations": recommendations.get("recommendations", []),
    }


async def ignore_non_php_jobs(
    _: Auth, body: ActionRunRequest, db: AsyncSession
):
    """Mark non-PHP jobs as filtered (not deleted)."""
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="confirm=True required. Preview with /actions/non-php-cleanup/preview first.",
        )
    from sqlalchemy import and_, not_, update as sa_update
    from services.api.models.db import Job

    condition = and_(
        not_(_php_match_expr(Job)),
        Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
    )
    result = await db.execute(
        sa_update(Job)
        .where(condition)
        .values(status="filtered")
        .execution_options(synchronize_session="fetch")
    )
    await db.commit()
    updated = result.rowcount
    logger.info("admin_ignore_non_php_jobs", updated=updated)
    return {"action": "non-php-cleanup", "updated": updated}


@router.post("/quick-actions/{action}")
async def quick_action(
    _: Auth,
    action: str,
    db: AsyncSession = Depends(get_db),
    confirm: bool = Query(False),
):
    """Trigger common maintenance tasks immediately."""
    action = action.strip().lower()
    meta = ACTION_REGISTRY.get(action)

    if action == "reset-email-discovery":
        return await _reset_email_discovery_action(db)

    if action == "priority-cover-emailed":
        return await _priority_cover_emailed_action(db)

    if action == "current-month-pipeline":
        return await _current_month_pipeline_action(db)

    if action == "non-php-cleanup":
        return await ignore_non_php_jobs(_, ActionRunRequest(confirm=confirm), db)

    if action == "generate-non-php-candidates":
        return await _generate_non_php_candidates_action(db)

    if not meta:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown action: {action}. Valid: {sorted(ACTION_REGISTRY.keys())}",
        )
    if meta["destructive"] and not confirm:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Action '{action}' requires confirm=true. "
                f"Preview it first with POST /admin/actions/{action}/preview."
            ),
        )

    task_name = meta.get("task")
    if not task_name:
        raise HTTPException(
            status_code=400,
            detail=f"Action '{action}' has no direct task handler.",
        )

    from services.scraper.celery_app import celery_app
    result = celery_app.send_task(task_name, queue=meta.get("queue"))
    logger.info("admin_quick_action_triggered", action=action, task_id=result.id)
    return {
        "action": action,
        "task_id": result.id,
        "status": "dispatched",
        "destructive": meta["destructive"],
        "queue": meta.get("queue"),
    }


async def _reset_email_discovery_action(db: AsyncSession):
    from sqlalchemy import update as sa_update
    from services.api.models.db import Job
    result = await db.execute(
        sa_update(Job)
        .where(Job.hr_email.is_(None))
        .where(Job.hr_email_discovery_status == "unreachable")
        .values(
            hr_email_discovery_status="pending",
            hr_email_discovery_attempts=0,
        )
    )
    await db.commit()
    reset_count = result.rowcount
    logger.info("admin_reset_email_discovery", reset_count=reset_count)
    return {"action": "reset-email-discovery", "reset": reset_count}


async def _priority_cover_emailed_action(db: AsyncSession):
    from sqlalchemy import select, func
    from services.api.models.db import Job
    result = await db.execute(
        select(func.count(Job.id))
        .where(Job.status == "sent")
        .where(
            (Job.cover_letter.is_(None)) |
            (Job.cover_letter_generated_at.is_(None))
        )
    )
    count = result.scalar() or 0
    if count > 0:
        from services.scraper.celery_app import celery_app
        task_result = celery_app.send_task(
            "services.ai.tasks.refresh_cover_letters_task",
            kwargs={"priority_emailed": True},
        )
        logger.info("admin_priority_cover_emailed", count=count, task_id=task_result.id)
        return {"action": "priority-cover-emailed", "task_id": task_result.id, "count": count}
    return {"action": "priority-cover-emailed", "count": 0, "status": "no_jobs_found"}


async def _current_month_pipeline_action(db: AsyncSession):
    from sqlalchemy import select, func, update as sa_update
    from services.api.models.db import Job
    from datetime import datetime, timezone
    month_start = datetime.now(timezone.utc).replace(tzinfo=None).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Job.id))
        .where(Job.scraped_at >= month_start)
        .where(Job.status.notin_(["sent", "bounced", "error", "filtered"]))
    )
    count = result.scalar() or 0
    from services.scraper.celery_app import celery_app
    task_ids = []
    if count > 0:
        r1 = celery_app.send_task("services.scraper.tasks.backfill_hr_emails_task")
        r2 = celery_app.send_task("services.ai.tasks.fill_missing_covers_task")
        task_ids = [r1.id, r2.id]
    logger.info("admin_current_month_pipeline", count=count, task_ids=task_ids)
    return {"action": "current-month-pipeline", "count": count, "task_ids": task_ids}


async def _generate_non_php_candidates_action(db: AsyncSession):
    from sqlalchemy import select, func, update as sa_update, and_, not_
    from services.api.models.db import Candidate, Job

    candidates = (await db.execute(
        select(Candidate).where(Candidate.is_active == True).limit(10)
    )).scalars().all()
    if not candidates:
        raise HTTPException(status_code=404, detail="No active candidates found")

    candidate = candidates[0]
    cover_text = candidate.static_cover_letter or ""

    if not cover_text and not candidate.cover_letter_template:
        raise HTTPException(
            status_code=422,
            detail=f"Candidate '{candidate.name}' has no static_cover_letter or cover_letter_template.",
        )

    condition = and_(
        not_(_php_match_expr(Job)),
        Job.status.notin_(ACTIVE_CLEANUP_STATUSES),
        Job.status != "filtered",
    )

    total = (await db.execute(select(func.count(Job.id)).where(condition))).scalar() or 0
    if total == 0:
        return {"action": "generate-non-php-candidates", "updated": 0, "status": "no_jobs_found"}

    result = await db.execute(
        sa_update(Job)
        .where(condition)
        .values(
            candidate_id=candidate.id,
            cover_letter=cover_text,
            status="cover_generated",
        )
        .execution_options(synchronize_session="fetch")
    )
    await db.commit()
    updated = result.rowcount
    logger.info(
        "admin_generate_non_php_candidates",
        candidate_id=candidate.id,
        candidate_name=candidate.name,
        updated=updated,
    )
    return {
        "action": "generate-non-php-candidates",
        "updated": updated,
        "candidate_id": candidate.id,
        "candidate_name": candidate.name,
        "cover_letter_source": "static_cover_letter" if candidate.static_cover_letter else "cover_letter_template",
    }


# ── Existing endpoints (preserved for backward compat) ───────────────────────

KNOWN_CRON_TASKS = [
    "scheduled_scrape",
    "backfill_hr_emails_task",
    "fix_placeholder_emails_task",
    "fill_missing_covers_task",
    "refresh_cover_letters_task",
    "deduplicate_jobs_task",
    "cleanup_old_jobs_task",
    "pipeline_health_check_task",
    "stale_lock_reaper_task",
    "check_cover_letter_status_task",
    "purge_old_cron_runs_task",
    "retry_failed_sends_task",
]

CRON_PROTECTED_TASKS = {
    "scheduled_scrape",
    "backfill_hr_emails_task",
    "fix_placeholder_emails_task",
    "fill_missing_covers_task",
    "refresh_cover_letters_task",
    "cleanup_old_jobs_task",
    "deduplicate_jobs_task",
    "pipeline_health_check_task",
    "stale_lock_reaper_task",
    "check_cover_letter_status_task",
    "purge_old_cron_runs_task",
    "retry_failed_sends_task",
}

# Maps task name → (dotted celery path, destination queue)
CRON_TASK_CELERY_MAP: dict[str, tuple[str, str]] = {
    "scheduled_scrape":              ("services.scraper.tasks.scheduled_scrape",            "jh_scraping_bulk"),
    "backfill_hr_emails_task":       ("services.scraper.tasks.backfill_hr_emails_task",      "jh_scraping_enrichment"),
    "fix_placeholder_emails_task":   ("services.scraper.tasks.fix_placeholder_emails_task",  "jh_scraping_enrichment"),
    "fill_missing_covers_task":      ("services.ai.tasks.fill_missing_covers_task",          "jh_cover_letter_bulk"),
    "refresh_cover_letters_task":    ("services.ai.tasks.refresh_cover_letters_task",        "jh_cover_letter_bulk"),
    "check_cover_letter_status_task":("services.ai.tasks.check_cover_letter_status_task",    "jh_cover_letter_bulk"),
    "deduplicate_jobs_task":         ("services.scraper.tasks.deduplicate_jobs_task",        "jh_jobs_maintenance"),
    "cleanup_old_jobs_task":         ("services.scraper.tasks.cleanup_old_jobs_task",        "jh_jobs_maintenance"),
    "pipeline_health_check_task":    ("services.scraper.tasks.pipeline_health_check_task",   "jh_jobs_maintenance"),
    "stale_lock_reaper_task":        ("services.scraper.tasks.stale_lock_reaper_task",       "jh_jobs_maintenance"),
    "purge_old_cron_runs_task":      ("services.scraper.tasks.purge_old_cron_runs_task",     "jh_jobs_maintenance"),
    "retry_failed_sends_task":       ("services.sender.tasks.retry_failed_sends_task",       "jh_email_retry"),
}


async def _get_task_stats(task_name: str) -> dict:
    """Fetch circuit breaker, lock, and rate limit state for a single task."""
    protected = task_name in CRON_PROTECTED_TASKS

    if not protected:
        return {
            "task": task_name,
            "cron_protected": False,
            "circuit_state": "n/a",
            "lock_active": False,
            "lock_ttl_seconds": 0,
            "runs_last_hour": 0,
            "recent_failures": 0,
            "last_run": {},
        }

    from services.common.cron_validators import (
        _CIRCUIT_PREFIX,
        _LAST_RUN_PREFIX,
        _LOCK_PREFIX,
        _RATE_PREFIX,
        _get_redis_conn,
    )
    redis = await _get_redis_conn()
    if not redis:
        return {"task": task_name, "cron_protected": True, "error": "Redis unavailable"}

    try:
        lock_key = f"{_LOCK_PREFIX}{task_name}"
        rate_key = f"{_RATE_PREFIX}{task_name}"
        circuit_key = f"{_CIRCUIT_PREFIX}{task_name}"
        last_run_key = f"{_LAST_RUN_PREFIX}{task_name}"

        lock_ttl = await redis.ttl(lock_key)
        rate_count = await redis.zcard(rate_key)
        circuit_state = await redis.get(f"{circuit_key}:state") or "closed"
        failures = await redis.zcard(f"{circuit_key}:failures")
        last_run = await redis.hgetall(last_run_key)

        return {
            "task": task_name,
            "cron_protected": True,
            "lock_active": lock_ttl > 0,
            "lock_ttl_seconds": lock_ttl if lock_ttl > 0 else 0,
            "runs_last_hour": rate_count,
            "circuit_state": circuit_state,
            "recent_failures": failures,
            "last_run": last_run,
        }
    except Exception as exc:
        return {"task": task_name, "cron_protected": True, "error": str(exc)}


@router.get("/cron/status")
async def get_cron_status(_: Auth):
    """Inspect circuit breaker, lock, and rate limit state for all cron tasks."""
    result = {}
    for task in KNOWN_CRON_TASKS:
        result[task] = await _get_task_stats(task)
    return result


@router.post("/cron/{task_name}/reset_circuit")
async def reset_cron_circuit(_: Auth, task_name: str):
    """Reset the circuit breaker for a stuck cron task."""
    if task_name not in KNOWN_CRON_TASKS:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_name}")
    from services.common.cron_validators import _CIRCUIT_PREFIX, _get_redis_conn
    redis = await _get_redis_conn()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    try:
        circuit_key = f"{_CIRCUIT_PREFIX}{task_name}"
        await redis.delete(f"{circuit_key}:state")
        await redis.delete(f"{circuit_key}:failures")
        await redis.delete(f"{circuit_key}:opened_at")
        logger.info("circuit_breaker_reset_via_api", task=task_name)
        return {"task": task_name, "reset": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cron/{task_name}/release_lock")
async def release_cron_lock(_: Auth, task_name: str):
    """Force-release a stuck singleton lock for a cron task."""
    if task_name not in KNOWN_CRON_TASKS:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_name}")
    from services.common.cron_validators import _LOCK_PREFIX, _get_redis_conn
    redis = await _get_redis_conn()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    try:
        lock_key = f"{_LOCK_PREFIX}{task_name}"
        deleted = await redis.delete(lock_key)
        logger.info("cron_lock_released_via_api", task=task_name, was_held=deleted > 0)
        return {"task": task_name, "lock_released": True, "was_held": deleted > 0}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/cron/{task_name}/reset_rate_limit")
async def reset_cron_rate_limit(_: Auth, task_name: str):
    """Clear the rate limit counter for a cron task."""
    if task_name not in KNOWN_CRON_TASKS:
        raise HTTPException(status_code=404, detail=f"Unknown task: {task_name}")
    from services.common.cron_validators import _RATE_PREFIX, _get_redis_conn
    redis = await _get_redis_conn()
    if not redis:
        raise HTTPException(status_code=503, detail="Redis unavailable")
    try:
        rate_key = f"{_RATE_PREFIX}{task_name}"
        await redis.delete(rate_key)
        logger.info("cron_rate_limit_cleared_via_api", task=task_name)
        return {"task": task_name, "rate_limit_cleared": True}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


class CronTriggerRequest(BaseModel):
    bypass_lock: bool = False
    bypass_rate_limit: bool = False


@router.post("/cron/{task_name}/trigger")
async def trigger_cron_task(_: Auth, task_name: str, body: CronTriggerRequest = None):
    """Directly trigger a cron task immediately, bypassing the beat schedule.

    bypass_lock: if True, releases the singleton lock before triggering so
                 even a currently-running task can have a second instance dispatched.
    bypass_rate_limit: if True, clears the rate-limit counter before triggering.
    """
    if task_name not in CRON_TASK_CELERY_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown task '{task_name}'. Valid: {sorted(CRON_TASK_CELERY_MAP.keys())}",
        )

    body = body or CronTriggerRequest()
    celery_path, queue = CRON_TASK_CELERY_MAP[task_name]

    from services.common.cron_validators import (
        _LOCK_PREFIX, _RATE_PREFIX, _get_redis_conn,
    )
    redis = await _get_redis_conn()

    bypassed: dict[str, bool] = {"lock": False, "rate_limit": False}
    warning: str | None = None

    if redis:
        if body.bypass_lock:
            lock_key = f"{_LOCK_PREFIX}{task_name}"
            lock_ttl = await redis.ttl(lock_key)
            if lock_ttl > 0:
                await redis.delete(lock_key)
                bypassed["lock"] = True
                warning = f"Lock was active (TTL {lock_ttl}s) — released. Two instances may run concurrently."
        if body.bypass_rate_limit:
            rate_key = f"{_RATE_PREFIX}{task_name}"
            await redis.delete(rate_key)
            bypassed["rate_limit"] = True

    from services.scraper.celery_app import celery_app
    result = celery_app.send_task(celery_path, queue=queue)
    logger.info("admin_cron_triggered", task=task_name, task_id=result.id, **bypassed)

    response: dict = {
        "task_name": task_name,
        "celery_task_id": result.id,
        "queue": queue,
        "triggered_by": "manual",
        "bypassed": bypassed,
    }
    if warning:
        response["warning"] = warning
    return response


@router.post("/reset-email-discovery")
async def reset_email_discovery(_: Auth, db: AsyncSession = Depends(get_db)):
    """Reset all 'unreachable' jobs back to pending so the backfill retries them."""
    return await _reset_email_discovery_action(db)


# ── Cron run history ──────────────────────────────────────────────────────────

@router.get("/cron/runs")
async def get_cron_runs(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    task: Optional[str] = Query(None, description="Filter by task name"),
    status: Optional[str] = Query(None, description="running|success|failure|timeout|skipped"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated history of cron task executions."""
    from services.api.models.db import CronRun
    from sqlalchemy import func as sa_func

    base_filter = []
    if task:
        base_filter.append(CronRun.task_name == task)
    if status:
        base_filter.append(CronRun.status == status)

    count_q = select(sa_func.count(CronRun.id))
    for cond in base_filter:
        count_q = count_q.where(cond)
    total_result = await db.execute(count_q)
    total = total_result.scalar() or 0

    q = select(CronRun).order_by(desc(CronRun.started_at))
    for cond in base_filter:
        q = q.where(cond)
    q = q.offset(offset).limit(limit)

    result = await db.execute(q)
    runs = result.scalars().all()

    items = [
        {
            "id": r.id,
            "task_name": r.task_name,
            "celery_task_id": r.celery_task_id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "duration_ms": r.duration_ms,
            "status": r.status,
            "error_summary": r.error_summary,
            "triggered_by": r.triggered_by,
            "worker_host": r.worker_host,
            "post_state": r.post_state,
            "steps_count": len(r.steps or []),
        }
        for r in runs
    ]

    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/cron/runs/{run_id}")
async def get_cron_run(
    _: Auth,
    run_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Full detail for a single cron run including steps and traceback."""
    from services.api.models.db import CronRun

    run = await db.get(CronRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    return {
        "id": run.id,
        "task_name": run.task_name,
        "celery_task_id": run.celery_task_id,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "ended_at": run.ended_at.isoformat() if run.ended_at else None,
        "duration_ms": run.duration_ms,
        "status": run.status,
        "error_summary": run.error_summary,
        "error_traceback": run.error_traceback,
        "pre_state": run.pre_state,
        "post_state": run.post_state,
        "steps": run.steps or [],
        "triggered_by": run.triggered_by,
        "worker_host": run.worker_host,
    }


@router.get("/cron/live")
async def cron_live_stream(_: Auth):
    """SSE stream of currently-running cron tasks (from Redis).

    Emits one JSON event per currently-running task every 3 seconds.
    Clients subscribe with EventSource('/admin/cron/live').
    """
    from services.api.core.cache import get_redis
    from services.common.cron_monitor import _REDIS_RUN_PREFIX

    async def event_generator() -> AsyncGenerator[str, None]:
        redis = await get_redis()
        try:
            while True:
                payload = []
                if redis:
                    try:
                        cursor = 0
                        run_keys = []
                        while True:
                            cursor, keys = await redis.scan(
                                cursor, match=f"{_REDIS_RUN_PREFIX}*", count=50
                            )
                            run_keys.extend(keys)
                            if cursor == 0:
                                break
                        for key in run_keys:
                            data = await redis.hgetall(key)
                            if data and data.get("status") == "running":
                                payload.append(data)
                    except Exception:
                        pass
                yield f"data: {json.dumps(payload)}\n\n"
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Cron Task Catalog ─────────────────────────────────────────────────────────

_CRON_TASK_CATALOG = [
    {"name": "scheduled_scrape", "queue": "jh_scraping_bulk", "schedule": "every 2h", "category": "scraping"},
    {"name": "backfill_hr_emails_task", "queue": "jh_scraping_enrichment", "schedule": "every 5m", "category": "scraping"},
    {"name": "fix_placeholder_emails_task", "queue": "jh_scraping_enrichment", "schedule": "every 30m", "category": "scraping"},
    {"name": "fill_missing_covers_task", "queue": "jh_cover_letter_bulk", "schedule": "every 5m", "category": "ai"},
    {"name": "refresh_cover_letters_task", "queue": "jh_cover_letter_bulk", "schedule": "every 4h", "category": "ai"},
    {"name": "check_cover_letter_status_task", "queue": "jh_cover_letter_bulk", "schedule": "every 1h", "category": "ai"},
    {"name": "deduplicate_jobs_task", "queue": "jh_jobs_maintenance", "schedule": "every 5m", "category": "maintenance"},
    {"name": "cleanup_old_jobs_task", "queue": "jh_jobs_maintenance", "schedule": "weekly", "category": "maintenance"},
    {"name": "stale_lock_reaper_task", "queue": "jh_jobs_maintenance", "schedule": "every 10m", "category": "maintenance"},
    {"name": "pipeline_health_check_task", "queue": "jh_jobs_maintenance", "schedule": "every 15m", "category": "maintenance"},
    {"name": "purge_old_cron_runs_task", "queue": "jh_jobs_maintenance", "schedule": "daily", "category": "maintenance"},
    {"name": "retry_failed_sends_task", "queue": "jh_email_retry", "schedule": "every 30m (disabled)", "category": "email"},
]


@router.get("/cron/tasks")
async def cron_task_catalog(_: Auth):
    """Return all known cron tasks with schedule and queue metadata."""
    return {"tasks": _CRON_TASK_CATALOG}


# ── Cron KPIs ──────────────────────────────────────────────────────────────────

@router.get("/cron/kpis")
async def cron_kpis(_: Auth, db: AsyncSession = Depends(get_db)):
    """Aggregated cron execution stats (computed from DB, not page-limited)."""
    from services.api.models.db import CronRun
    from sqlalchemy import func as sa_func, text as sa_text
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    h24 = now - timedelta(hours=24)
    h1 = now - timedelta(hours=1)

    running_q = await db.execute(
        select(sa_func.count(CronRun.id)).where(CronRun.status == "running")
    )
    running_now = running_q.scalar() or 0

    failures_24h_q = await db.execute(
        select(sa_func.count(CronRun.id))
        .where(CronRun.status == "failure")
        .where(CronRun.started_at >= h24)
    )
    failures_24h = failures_24h_q.scalar() or 0

    total_24h_q = await db.execute(
        select(sa_func.count(CronRun.id))
        .where(CronRun.started_at >= h24)
    )
    total_24h = total_24h_q.scalar() or 0

    avg_dur_q = await db.execute(
        select(sa_func.avg(CronRun.duration_ms))
        .where(CronRun.status == "success")
        .where(CronRun.started_at >= h24)
    )
    avg_duration_ms = avg_dur_q.scalar()
    avg_duration_ms = int(avg_duration_ms) if avg_duration_ms else None

    success_rate = round((total_24h - failures_24h) / total_24h, 3) if total_24h > 0 else None

    return {
        "running_now": running_now,
        "failures_24h": failures_24h,
        "total_runs_24h": total_24h,
        "success_rate_24h": success_rate,
        "avg_duration_ms": avg_duration_ms,
    }


# ── Admin Summary (reduce polling load) ────────────────────────────────────────

@router.get("/summary")
async def admin_summary(_: Auth):
    """Combined summary for the admin page header — replaces multiple parallel calls."""
    health = await check_system_health()
    queues = await get_queue_stats()
    mode = get_current_performance_mode()

    total_queue_msgs = sum(q.get("messages", 0) for q in queues)
    active_queues = sum(1 for q in queues if q.get("messages", 0) > 0)
    total_consumers = sum(q.get("consumers", 0) for q in queues)

    return {
        "health": health,
        "queues": {
            "total": len(queues),
            "active": active_queues,
            "total_messages": total_queue_msgs,
            "total_consumers": total_consumers,
            "items": queues,
        },
        "performance_mode": mode,
    }


# ── Worker Paused State ───────────────────────────────────────────────────────

@router.get("/workers/paused")
async def workers_paused_state(_: Auth):
    """Get the paused state for all workers (tracked in Redis)."""
    from services.api.services.admin_service import _WORKER_PAUSED_PREFIX
    from services.api.core.cache import get_redis

    redis = await get_redis()
    if not redis:
        return {"paused_services": [], "error": "Redis unavailable"}

    paused_services: list[str] = []
    try:
        cursor = 0
        while True:
            cursor, keys = await redis.scan(
                cursor, match=f"{_WORKER_PAUSED_PREFIX}*", count=100
            )
            for key in keys:
                svc = key.removeprefix(_WORKER_PAUSED_PREFIX)
                paused_services.append(svc)
            if cursor == 0:
                break
    except Exception as exc:
        return {"paused_services": [], "error": str(exc)}

    return {"paused_services": paused_services}


# ── Quota status ──────────────────────────────────────────────────────────────

@router.get("/quota")
async def get_quota_status(_: Auth):
    """Current usage for Groq RPM quota."""
    from services.ai.rate_limiter import get_groq_rate_status

    groq_status = await get_groq_rate_status()
    return {"groq": groq_status}


# ── Database Monitoring ──────────────────────────────────────────────────────

@router.get("/db/health")
async def db_health(_: Auth, db: AsyncSession = Depends(get_db)):
    """Check database connection pool health and latency."""
    import time as _time
    from sqlalchemy import text as sa_text

    latency_ms = 0.0
    ok = False
    try:
        start = _time.monotonic()
        await db.execute(sa_text("SELECT 1"))
        latency_ms = round((_time.monotonic() - start) * 1000, 2)
        ok = True
    except Exception as exc:
        return {"status": "error", "error": str(exc)}

    pool = db.get_bind().pool
    return {
        "status": "ok" if ok else "error",
        "latency_ms": latency_ms,
        "pool": {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "max_size": pool.size() + (pool._max_overflow if hasattr(pool, '_max_overflow') else 0),
        },
    }


@router.get("/db/tables")
async def db_tables(_: Auth, db: AsyncSession = Depends(get_db)):
    """Row counts for all major tables."""
    from sqlalchemy import text as sa_text
    from services.api.models.db import (
        Job, Candidate, SendLog, CronRun, SearchTask,
        Embedding, BlacklistedCompany, User, Tenant,
    )

    tables = {
        "jobs": Job.__tablename__,
        "candidates": Candidate.__tablename__,
        "send_logs": SendLog.__tablename__,
        "cron_runs": CronRun.__tablename__,
        "search_tasks": SearchTask.__tablename__,
        "embeddings": Embedding.__tablename__,
        "blacklisted_companies": BlacklistedCompany.__tablename__,
        "users": User.__tablename__,
        "tenants": Tenant.__tablename__,
    }

    result_data = {}
    for label, table_name in tables.items():
        try:
            r = await db.execute(sa_text(f"SELECT COUNT(*) FROM {table_name}"))
            result_data[label] = {"table": table_name, "count": r.scalar() or 0}
        except Exception as exc:
            result_data[label] = {"table": table_name, "error": str(exc)}

    job_status_r = await db.execute(
        sa_text("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status ORDER BY cnt DESC")
    )
    result_data["jobs_by_status"] = {row[0]: row[1] for row in job_status_r.fetchall()}

    return result_data


@router.get("/db/slow-queries")
async def db_slow_queries(_: Auth, db: AsyncSession = Depends(get_db)):
    """Top 10 slowest queries from pg_stat_statements."""
    from sqlalchemy import text as sa_text

    try:
        await db.execute(sa_text("CREATE EXTENSION IF NOT EXISTS pg_stat_statements"))
    except Exception:
        pass

    try:
        r = await db.execute(sa_text("""
            SELECT
                LEFT(query, 200) as query,
                calls,
                ROUND(total_exec_time::numeric, 2) as total_ms,
                ROUND(mean_exec_time::numeric, 2) as mean_ms,
                ROUND(max_exec_time::numeric, 2) as max_ms
            FROM pg_stat_statements
            WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
            ORDER BY total_exec_time DESC
            LIMIT 10
        """))
        rows = r.fetchall()
        queries = [
            {
                "query": row[0],
                "calls": row[1],
                "total_ms": float(row[2]),
                "mean_ms": float(row[3]),
                "max_ms": float(row[4]),
            }
            for row in rows
        ]
        return {"queries": queries, "count": len(queries)}
    except Exception as exc:
        return {"error": str(exc), "suggestion": "pg_stat_statements extension may not be available. Add 'shared_preload_libraries = pg_stat_statements' to postgresql.conf and restart."}


@router.get("/db/size")
async def db_size(_: Auth, db: AsyncSession = Depends(get_db)):
    """Database and table sizes."""
    from sqlalchemy import text as sa_text

    db_size_r = await db.execute(sa_text(
        "SELECT pg_size_pretty(pg_database_size(current_database())) as size, pg_database_size(current_database()) as bytes"
    ))
    db_row = db_size_r.fetchone()

    tables_r = await db.execute(sa_text("""
        SELECT
            schemaname || '.' || relname as table_name,
            pg_size_pretty(pg_total_relation_size(relid)) as total_size,
            pg_size_pretty(pg_relation_size(relid)) as data_size,
            pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) as index_size,
            pg_total_relation_size(relid) as total_bytes
        FROM pg_catalog.pg_statio_user_tables
        ORDER BY pg_total_relation_size(relid) DESC
        LIMIT 20
    """))
    tables = [
        {
            "table": row[0],
            "total_size": row[1],
            "data_size": row[2],
            "index_size": row[3],
            "total_bytes": row[4],
        }
        for row in tables_r.fetchall()
    ]

    return {
        "database": {"size": db_row[0], "bytes": db_row[1]},
        "tables": tables,
    }


@router.get("/db/migrations")
async def db_migrations(_: Auth):
    """Current Alembic migration status."""
    import subprocess
    from pathlib import Path

    project_root = Path(__file__).resolve().parents[4]
    alembic_ini = project_root / "backend" / "alembic.ini"

    if not alembic_ini.exists():
        return {"error": "alembic.ini not found"}

    try:
        result = subprocess.run(
            ["alembic", "current"],
            cwd=str(alembic_ini.parent),
            capture_output=True, text=True, timeout=10,
        )
        current = result.stdout.strip() or result.stderr.strip()

        result_pending = subprocess.run(
            ["alembic", "heads"],
            cwd=str(alembic_ini.parent),
            capture_output=True, text=True, timeout=10,
        )
        heads = result_pending.stdout.strip() or result_pending.stderr.strip()

        return {"current": current, "heads": heads, "raw_output": current}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/db/locks")
async def db_locks(_: Auth, db: AsyncSession = Depends(get_db)):
    """Detect active locks and blocking queries."""
    from sqlalchemy import text as sa_text

    r = await db.execute(sa_text("""
        SELECT
            blocked.pid AS blocked_pid,
            blocked.query AS blocked_query,
            blocking.pid AS blocking_pid,
            blocking.query AS blocking_query,
            blocked_locks.locktype AS lock_type,
            blocked_locks.mode AS lock_mode
        FROM pg_locks blocked_locks
        JOIN pg_stat_activity blocked ON blocked.pid = blocked_locks.pid
        JOIN pg_locks blocking_locks
            ON blocking_locks.locktype = blocked_locks.locktype
            AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
            AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
            AND blocking_locks.pid != blocked_locks.pid
        JOIN pg_stat_activity blocking ON blocking.pid = blocking_locks.pid
        WHERE NOT blocked_locks.granted
        LIMIT 20
    """))
    locks = [
        {
            "blocked_pid": row[0],
            "blocked_query": row[1][:200] if row[1] else None,
            "blocking_pid": row[2],
            "blocking_query": row[3][:200] if row[3] else None,
            "lock_type": row[4],
            "lock_mode": row[5],
        }
        for row in r.fetchall()
    ]

    active_r = await db.execute(sa_text("""
        SELECT COUNT(*) FROM pg_locks WHERE NOT granted
    """))
    waiting_count = active_r.scalar() or 0

    return {"blocking_locks": locks, "waiting_queries": waiting_count}


# ── Redis Monitoring ──────────────────────────────────────────────────────────

@router.get("/redis/health")
async def redis_health(_: Auth):
    """Redis server health and memory stats."""
    from services.api.core.cache import get_redis

    redis = await get_redis()
    if not redis:
        return {"status": "error", "error": "Redis unavailable"}

    try:
        info = await redis.info()
        return {
            "status": "ok",
            "version": info.get("redis_version"),
            "uptime_seconds": info.get("uptime_in_seconds"),
            "uptime_days": info.get("uptime_in_days"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_human": info.get("used_memory_human"),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "maxmemory_human": info.get("maxmemory_human", "unlimited"),
            "used_memory_percent": round(
                info.get("used_memory", 0) / info["maxmemory"] * 100, 1
            ) if info.get("maxmemory", 0) > 0 else None,
            "total_commands_processed": info.get("total_commands_processed"),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
            "hit_rate_percent": round(
                info.get("keyspace_hits", 0)
                / max(info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0), 1) * 100,
                1,
            ),
            "evicted_keys": info.get("evicted_keys"),
            "expired_keys": info.get("expired_keys"),
            "connected_slaves": info.get("connected_slaves", 0),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


@router.get("/redis/keyspace")
async def redis_keyspace(_: Auth):
    """Redis keyspace breakdown by prefix pattern."""
    from services.api.core.cache import get_redis

    redis = await get_redis()
    if not redis:
        return {"error": "Redis unavailable"}

    try:
        info = await redis.info("keyspace")
        db_stats = {}
        for db_key, db_val in info.items():
            if isinstance(db_val, str) and "keys=" in db_val:
                parts = dict(p.split("=") for p in db_val.split(",") if "=" in p)
                db_stats[db_key] = {
                    "keys": int(parts.get("keys", 0)),
                    "expires": int(parts.get("expires", 0)),
                    "avg_ttl": int(parts.get("avg_ttl", 0)),
                }

        prefix_counts = {}
        prefixes = [
            "admin:", "cron:", "jobs:", "stats:", "candidates:",
            "rl:", "search_tasks:", "send_logs:", "celery-task-meta-",
        ]
        for prefix in prefixes:
            try:
                count = 0
                cursor = 0
                while True:
                    cursor, keys = await redis.scan(cursor, match=f"{prefix}*", count=200)
                    count += len(keys)
                    if cursor == 0:
                        break
                prefix_counts[prefix] = count
            except Exception:
                prefix_counts[prefix] = "error"

        return {"databases": db_stats, "prefix_counts": prefix_counts}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/redis/cache-stats")
async def redis_cache_stats(_: Auth):
    """Cache performance metrics."""
    from services.api.core.cache import get_redis

    redis = await get_redis()
    if not redis:
        return {"error": "Redis unavailable"}

    try:
        info = await redis.info("stats")
        memory_info = await redis.info("memory")

        hits = info.get("keyspace_hits", 0)
        misses = info.get("keyspace_misses", 0)
        total = hits + misses

        return {
            "keyspace_hits": hits,
            "keyspace_misses": misses,
            "hit_rate_percent": round(hits / max(total, 1) * 100, 1),
            "total_requests": total,
            "evicted_keys": info.get("evicted_keys", 0),
            "expired_keys": info.get("expired_keys", 0),
            "used_memory_human": memory_info.get("used_memory_human"),
            "used_memory_peak_human": memory_info.get("used_memory_peak_human"),
            "fragmentation_ratio": memory_info.get("mem_fragmentation_ratio"),
        }
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/redis/pubsub")
async def redis_pubsub(_: Auth):
    """Active Pub/Sub channels and subscribers."""
    from services.api.core.cache import get_redis

    redis = await get_redis()
    if not redis:
        return {"error": "Redis unavailable"}

    try:
        channels = await redis.pubsub_numsub()
        active = [
            {"channel": ch, "subscribers": count}
            for ch, count in channels
            if count > 0
        ]
        num_channels = len(await redis.pubsub_channels() or [])
        return {
            "total_channels": num_channels,
            "active_channels": active,
            "active_count": len(active),
        }
    except Exception as exc:
        return {"error": str(exc)}


# ── System Resources ──────────────────────────────────────────────────────────

@router.get("/system/resources")
async def system_resources(_: Auth):
    """Per-container CPU, memory, and disk usage."""
    try:
        status = await get_docker_status()
        if isinstance(status, dict) and "error" in status:
            return {"error": "Docker agent unavailable", "detail": status["error"]}
        return {"containers": status}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/system/uptime")
async def system_uptime(_: Auth):
    """Container start times and uptime."""
    import subprocess
    from pathlib import Path
    from datetime import datetime, timezone

    project_root = Path(__file__).resolve().parents[4]
    compose_file = project_root / "infra" / "docker-compose.yml"

    try:
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_file), "ps", "--format", "json"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return {"error": result.stderr[:500]}

        services = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                import json as _json
                c = _json.loads(line)
                services.append({
                    "service": c.get("Service", c.get("service", "unknown")),
                    "state": c.get("State", c.get("state", "")),
                    "status": c.get("Status", c.get("status", "")),
                    "health": c.get("Health", c.get("health", "")),
                })
            except Exception:
                continue

        return {"services": services}
    except Exception as exc:
        return {"error": str(exc)}


@router.get("/system/env-check")
async def system_env_check(_: Auth):
    """Validate critical environment variables (values masked)."""
    import os

    required_vars = [
        ("DATABASE_URL", "Database connection"),
        ("REDIS_URL", "Redis connection"),
        ("GROQ_API_KEY", "Groq LLM API"),
        ("RESEND_API_KEY", "Email sending (Resend)"),
        ("SECRET_KEY", "JWT secret"),
    ]

    optional_vars = [
        ("RABBITMQ_URL", "RabbitMQ broker"),
        ("CLOUDFLARE_R2_*", "File storage"),
        ("PINECONE_API_KEY", "Vector DB"),
    ]

    def check_var(name: str) -> dict:
        val = os.environ.get(name, "")
        present = bool(val)
        masked = f"{val[:4]}...{val[-4:]}" if present and len(val) > 12 else ("***" if present else "MISSING")
        return {"present": present, "value": masked}

    result = {
        "required": {name: {**check_var(name), "description": desc} for name, desc in required_vars},
        "optional": {name: {**check_var(name), "description": desc} for name, desc in optional_vars},
    }
    return result


@router.get("/system/latency")
async def system_latency(_: Auth):
    """API response latency metrics."""
    import time as _time
    import httpx

    latencies = {}
    endpoints = [
        ("/health", "Health check"),
        ("/admin/system/health", "System health"),
    ]

    for path, label in endpoints:
        try:
            start = _time.monotonic()
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(f"http://localhost:8000{path}")
            elapsed = round((_time.monotonic() - start) * 1000, 1)
            latencies[label] = {"path": path, "latency_ms": elapsed}
        except Exception as exc:
            latencies[label] = {"path": path, "error": str(exc)}

    return {"endpoints": latencies}


# ── Pipeline Monitoring ──────────────────────────────────────────────────────

@router.get("/pipeline/status")
async def pipeline_status(_: Auth, db: AsyncSession = Depends(get_db)):
    """Job counts by status - the full application pipeline."""
    from sqlalchemy import text as sa_text, func as sa_func
    from services.api.models.db import Job

    status_r = await db.execute(
        sa_text("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status ORDER BY cnt DESC")
    )
    by_status = {row[0]: row[1] for row in status_r.fetchall()}

    total_r = await db.execute(sa_text("SELECT COUNT(*) FROM jobs"))
    total = total_r.scalar() or 0

    terminal = sum(by_status.get(s, 0) for s in ["sent", "bounced", "error", "filtered"])
    active = total - terminal

    pipeline_order = [
        "new", "scraped", "scored", "cover_generated", "hr_found",
        "email_queued", "sent", "bounced", "error", "filtered",
    ]

    return {
        "total_jobs": total,
        "active": active,
        "terminal": terminal,
        "by_status": {s: by_status.get(s, 0) for s in pipeline_order if s in by_status},
        "other": {s: c for s, c in by_status.items() if s not in pipeline_order},
    }


@router.get("/pipeline/speed")
async def pipeline_speed(_: Auth, db: AsyncSession = Depends(get_db)):
    """Processing throughput over the last hour."""
    from sqlalchemy import text as sa_text
    from datetime import datetime, timedelta, timezone

    one_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)

    metrics = {}
    queries = {
        "jobs_scraped": (
            "SELECT COUNT(*) FROM jobs WHERE scraped_at >= :ts", {"ts": one_hour_ago}
        ),
        "covers_generated": (
            "SELECT COUNT(*) FROM jobs WHERE cover_letter_generated_at >= :ts AND cover_letter IS NOT NULL",
            {"ts": one_hour_ago},
        ),
        "emails_sent": (
            "SELECT COUNT(*) FROM send_logs WHERE sent_at >= :ts",
            {"ts": one_hour_ago},
        ),
        "hr_emails_found": (
            "SELECT COUNT(*) FROM jobs WHERE hr_email_discovered_at >= :ts AND hr_email IS NOT NULL",
            {"ts": one_hour_ago},
        ),
    }

    for label, (query, params) in queries.items():
        try:
            r = await db.execute(sa_text(query), params)
            count = r.scalar() or 0
            metrics[label] = {
                "count": count,
                "per_minute": round(count / 60, 2),
            }
        except Exception as exc:
            metrics[label] = {"error": str(exc)}

    return {"period": "last_1_hour", "metrics": metrics}


@router.get("/pipeline/failures")
async def pipeline_failures(_: Auth, db: AsyncSession = Depends(get_db)):
    """Failure trends and error analysis."""
    from sqlalchemy import text as sa_text
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    failed_crons_r = await db.execute(sa_text(
        "SELECT COUNT(*) FROM cron_runs WHERE status = 'failure' AND started_at >= :ts"
    ), {"ts": now - timedelta(hours=24)})
    failed_crons_24h = failed_crons_r.scalar() or 0

    recent_failed_r = await db.execute(sa_text(
        "SELECT task_name, error_summary, started_at FROM cron_runs "
        "WHERE status = 'failure' ORDER BY started_at DESC LIMIT 10"
    ))
    recent_failures = [
        {"task": row[0], "error": row[1], "started_at": row[2].isoformat() if row[2] else None}
        for row in recent_failed_r.fetchall()
    ]

    failed_by_task_r = await db.execute(sa_text(
        "SELECT task_name, COUNT(*) as cnt FROM cron_runs "
        "WHERE status = 'failure' AND started_at >= :ts "
        "GROUP BY task_name ORDER BY cnt DESC LIMIT 10"
    ), {"ts": now - timedelta(hours=24)})
    by_task = [{"task": row[0], "failures": row[1]} for row in failed_by_task_r.fetchall()]

    bounced_emails_r = await db.execute(sa_text(
        "SELECT COUNT(*) FROM send_logs WHERE status IN ('bounced', 'soft_bounce') AND sent_at >= :ts"
    ), {"ts": now - timedelta(hours=24)})
    bounced_emails = bounced_emails_r.scalar() or 0

    return {
        "period": "last_24_hours",
        "failed_cron_runs": failed_crons_24h,
        "bounced_emails": bounced_emails,
        "failures_by_task": by_task,
        "recent_failures": recent_failures,
    }


@router.get("/workers/throughput")
async def workers_throughput(_: Auth):
    """Per-worker task throughput metrics."""
    try:
        events = await get_recent_events(200)
    except Exception:
        events = []

    worker_stats: dict[str, dict] = {}
    for ev in events:
        worker_name = ev.get("hostname", "unknown")
        event_type = ev.get("type", "")
        if worker_name not in worker_stats:
            worker_stats[worker_name] = {
                "tasks_started": 0, "tasks_succeeded": 0, "tasks_failed": 0,
            }
        if "task-started" in event_type:
            worker_stats[worker_name]["tasks_started"] += 1
        elif "task-succeeded" in event_type:
            worker_stats[worker_name]["tasks_succeeded"] += 1
        elif "task-failed" in event_type:
            worker_stats[worker_name]["tasks_failed"] += 1

    return {"workers": worker_stats, "event_window": "last_200_events"}


# ── Admin Job Management ──────────────────────────────────────────────────────

_JOB_STATUSES = {
    "new", "scraped", "scored", "cover_generated", "hr_found",
    "email_queued", "pending_approval", "sent", "bounced",
    "error", "filtered", "unreachable",
}

_HR_DISCOVERY_STATUSES = {"pending", "found", "not_found", "unreachable"}


class AdminJobUpdateRequest(BaseModel):
    status: str | None = None
    hr_email: str | None = None
    relevance_score: float | None = None
    cover_letter: str | None = None
    hr_email_discovery_status: str | None = None


class AdminJobBulkUpdateRequest(BaseModel):
    job_ids: list[str]
    status: str
    dry_run: bool = False


class AdminJobBulkDeleteRequest(BaseModel):
    job_ids: list[str]


@router.get("/jobs")
async def admin_list_jobs(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    company: Optional[str] = Query(None),
    portal: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="ilike match on job_title or company"),
    candidate_id: Optional[str] = Query(None),
    min_score: Optional[float] = Query(None),
    has_hr_email: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Search and filter jobs across all tenants (operator view, no tenant scoping)."""
    from services.api.models.db import Job
    from sqlalchemy import func as sa_func, or_

    conditions = []
    if status:
        conditions.append(Job.status == status)
    if company:
        conditions.append(Job.company.ilike(f"%{company}%"))
    if portal:
        conditions.append(Job.source_portal == portal)
    if search:
        conditions.append(or_(
            Job.job_title.ilike(f"%{search}%"),
            Job.company.ilike(f"%{search}%"),
        ))
    if candidate_id:
        conditions.append(Job.candidate_id == candidate_id)
    if min_score is not None:
        conditions.append(Job.relevance_score >= min_score)
    if has_hr_email is True:
        conditions.append(Job.hr_email.isnot(None))
    elif has_hr_email is False:
        conditions.append(Job.hr_email.is_(None))

    count_q = select(sa_func.count(Job.id))
    for c in conditions:
        count_q = count_q.where(c)
    total = (await db.execute(count_q)).scalar() or 0

    q = select(
        Job.id, Job.job_title, Job.company, Job.location, Job.status,
        Job.source_portal, Job.hr_email, Job.relevance_score,
        Job.scraped_at, Job.candidate_id, Job.tenant_id,
        Job.hr_email_discovery_status, Job.cover_letter_generated_at,
    ).order_by(desc(Job.scraped_at)).offset(offset).limit(limit)
    for c in conditions:
        q = q.where(c)

    rows = (await db.execute(q)).fetchall()
    items = [
        {
            "id": r.id,
            "job_title": r.job_title,
            "company": r.company,
            "location": r.location,
            "status": r.status,
            "source_portal": r.source_portal,
            "hr_email": r.hr_email,
            "relevance_score": r.relevance_score,
            "scraped_at": r.scraped_at.isoformat() if r.scraped_at else None,
            "candidate_id": str(r.candidate_id) if r.candidate_id else None,
            "tenant_id": str(r.tenant_id) if r.tenant_id else None,
            "hr_email_discovery_status": r.hr_email_discovery_status,
            "has_cover": r.cover_letter_generated_at is not None,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/jobs/bulk-update")
async def admin_bulk_update_jobs(
    _: Auth,
    body: AdminJobBulkUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Bulk update status for a list of jobs (max 200)."""
    from services.api.models.db import Job
    from sqlalchemy import update as sa_update

    if not body.job_ids:
        raise HTTPException(status_code=400, detail="job_ids is required")
    if len(body.job_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 jobs per bulk operation")
    if body.status not in _JOB_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {sorted(_JOB_STATUSES)}")
    if body.dry_run:
        return {"dry_run": True, "would_update": len(body.job_ids), "status": body.status}

    result = await db.execute(
        sa_update(Job).where(Job.id.in_(body.job_ids)).values(status=body.status)
    )
    await db.commit()
    logger.info("admin_bulk_jobs_updated", count=result.rowcount, status=body.status)
    return {"updated": result.rowcount, "status": body.status, "dry_run": False}


@router.delete("/jobs/bulk-delete")
async def admin_bulk_delete_jobs(
    _: Auth,
    body: AdminJobBulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
):
    """Hard delete a batch of jobs and their send_logs/embeddings (max 200)."""
    from services.api.models.db import Job, SendLog, Embedding
    from sqlalchemy import delete as sa_delete

    if not body.job_ids:
        raise HTTPException(status_code=400, detail="job_ids is required")
    if len(body.job_ids) > 200:
        raise HTTPException(status_code=400, detail="Maximum 200 jobs per bulk operation")

    await db.execute(sa_delete(SendLog).where(SendLog.job_id.in_(body.job_ids)))
    await db.execute(sa_delete(Embedding).where(Embedding.job_id.in_(body.job_ids)))
    result = await db.execute(sa_delete(Job).where(Job.id.in_(body.job_ids)))
    await db.commit()
    logger.info("admin_bulk_jobs_deleted", count=result.rowcount)
    return {"deleted": result.rowcount}


@router.get("/jobs/{job_id}")
async def admin_get_job(_: Auth, job_id: str, db: AsyncSession = Depends(get_db)):
    """Full job detail including cover letter text and score breakdown."""
    from services.api.models.db import Job

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "id": job.id,
        "job_title": job.job_title,
        "company": job.company,
        "location": job.location,
        "job_description": job.job_description,
        "job_url": job.job_url,
        "status": job.status,
        "source_portal": job.source_portal,
        "hr_email": job.hr_email,
        "hr_email_discovery_status": job.hr_email_discovery_status,
        "hr_email_discovery_attempts": job.hr_email_discovery_attempts,
        "relevance_score": job.relevance_score,
        "score_breakdown": job.score_breakdown,
        "cover_letter": job.cover_letter,
        "cover_letter_generated_at": job.cover_letter_generated_at.isoformat() if job.cover_letter_generated_at else None,
        "scraped_at": job.scraped_at.isoformat() if job.scraped_at else None,
        "posted_date": job.posted_date.isoformat() if job.posted_date else None,
        "candidate_id": str(job.candidate_id) if job.candidate_id else None,
        "tenant_id": str(job.tenant_id) if job.tenant_id else None,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "job_type": job.job_type,
        "experience_required": job.experience_required,
    }


@router.patch("/jobs/{job_id}")
async def admin_update_job(
    _: Auth,
    job_id: str,
    body: AdminJobUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update mutable fields on any job (no tenant scoping)."""
    from services.api.models.db import Job

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    if "status" in updates and updates["status"] not in _JOB_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Valid: {sorted(_JOB_STATUSES)}")
    if "hr_email_discovery_status" in updates and updates["hr_email_discovery_status"] not in _HR_DISCOVERY_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid discovery status. Valid: {sorted(_HR_DISCOVERY_STATUSES)}")

    for field, value in updates.items():
        setattr(job, field, value)

    await db.commit()
    await db.refresh(job)
    logger.info("admin_job_updated", job_id=job_id, fields=list(updates.keys()))
    return {"updated": True, "job_id": job_id, "fields": list(updates.keys())}


@router.delete("/jobs/{job_id}")
async def admin_delete_job(_: Auth, job_id: str, db: AsyncSession = Depends(get_db)):
    """Hard delete a job and its associated send_logs and embeddings."""
    from services.api.models.db import Job, SendLog, Embedding
    from sqlalchemy import delete as sa_delete

    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    await db.execute(sa_delete(SendLog).where(SendLog.job_id == job_id))
    await db.execute(sa_delete(Embedding).where(Embedding.job_id == job_id))
    await db.delete(job)
    await db.commit()
    logger.info("admin_job_deleted", job_id=job_id)
    return {"deleted": True, "job_id": job_id}


# ── Admin Candidate Management ────────────────────────────────────────────────

class AdminCandidateUpdateRequest(BaseModel):
    name: str | None = None
    email: str | None = None
    skills: list | None = None
    target_roles: list | None = None
    target_locations: list | None = None
    bio: str | None = None
    years_experience: int | None = None
    is_active: bool | None = None
    cover_letter_template: str | None = None
    static_cover_letter: str | None = None


@router.get("/candidates")
async def admin_list_candidates(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    include_inactive: bool = Query(True),
):
    """List all candidates across all tenants (including inactive)."""
    from services.api.models.db import Candidate
    from sqlalchemy import func as sa_func

    q = select(
        Candidate.id, Candidate.name, Candidate.email, Candidate.is_active,
        Candidate.years_experience, Candidate.target_roles, Candidate.tenant_id,
        Candidate.linkedin_url, Candidate.github_url,
    )
    if not include_inactive:
        q = q.where(Candidate.is_active.is_(True))
    q = q.order_by(Candidate.name)

    rows = (await db.execute(q)).fetchall()
    items = [
        {
            "id": str(r.id),
            "name": r.name,
            "email": r.email,
            "is_active": r.is_active,
            "years_experience": r.years_experience,
            "target_roles": r.target_roles,
            "tenant_id": str(r.tenant_id) if r.tenant_id else None,
            "linkedin_url": r.linkedin_url,
            "github_url": r.github_url,
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/candidates/{candidate_id}")
async def admin_get_candidate(
    _: Auth,
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Full candidate profile including cover letter template and static cover letter."""
    from services.api.models.db import Candidate

    c = await db.get(Candidate, candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return {
        "id": str(c.id),
        "name": c.name,
        "email": c.email,
        "is_active": c.is_active,
        "years_experience": c.years_experience,
        "skills": c.skills,
        "target_roles": c.target_roles,
        "target_locations": c.target_locations,
        "bio": c.bio,
        "linkedin_url": c.linkedin_url,
        "github_url": c.github_url,
        "resume_url": c.resume_url,
        "tenant_id": str(c.tenant_id) if c.tenant_id else None,
        "cover_letter_template": c.cover_letter_template,
        "static_cover_letter": c.static_cover_letter,
    }


@router.patch("/candidates/{candidate_id}")
async def admin_update_candidate(
    _: Auth,
    candidate_id: str,
    body: AdminCandidateUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update any candidate field (no tenant scoping)."""
    from services.api.models.db import Candidate

    c = await db.get(Candidate, candidate_id)
    if not c:
        raise HTTPException(status_code=404, detail="Candidate not found")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    for field, value in updates.items():
        setattr(c, field, value)

    await db.commit()
    await db.refresh(c)
    logger.info("admin_candidate_updated", candidate_id=candidate_id, fields=list(updates.keys()))
    return {"updated": True, "candidate_id": candidate_id, "fields": list(updates.keys())}


# ── Admin Send Logs Analytics ─────────────────────────────────────────────────

@router.get("/send-logs")
async def admin_send_logs(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    candidate_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    sent_after: Optional[str] = Query(None, description="ISO date string e.g. 2024-01-01"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Extended send log query with job details, for operator use."""
    from services.api.models.db import SendLog, Job
    from sqlalchemy import func as sa_func, outerjoin
    from sqlalchemy.orm import aliased
    from datetime import datetime

    conditions = []
    if candidate_id:
        conditions.append(SendLog.candidate_id == candidate_id)
    if status:
        conditions.append(SendLog.status == status)
    if sent_after:
        try:
            since = datetime.fromisoformat(sent_after)
            conditions.append(SendLog.sent_at >= since)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid sent_after format, use ISO date")

    count_q = select(sa_func.count(SendLog.id))
    for c in conditions:
        count_q = count_q.where(c)
    total = (await db.execute(count_q)).scalar() or 0

    q = (
        select(
            SendLog.id, SendLog.job_id, SendLog.candidate_id, SendLog.to_email,
            SendLog.subject, SendLog.status, SendLog.provider,
            SendLog.sent_at, SendLog.delivered_at, SendLog.opened_at, SendLog.clicked_at,
            SendLog.error_message, SendLog.retry_count,
            Job.job_title, Job.company, Job.source_portal,
        )
        .outerjoin(Job, SendLog.job_id == Job.id)
        .order_by(desc(SendLog.sent_at))
        .offset(offset)
        .limit(limit)
    )
    for c in conditions:
        q = q.where(c)

    rows = (await db.execute(q)).fetchall()
    items = [
        {
            "id": str(r.id),
            "job_id": str(r.job_id) if r.job_id else None,
            "candidate_id": str(r.candidate_id) if r.candidate_id else None,
            "to_email": r.to_email,
            "subject": r.subject,
            "status": r.status,
            "provider": r.provider,
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "delivered_at": r.delivered_at.isoformat() if r.delivered_at else None,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "clicked_at": r.clicked_at.isoformat() if r.clicked_at else None,
            "error_message": r.error_message,
            "retry_count": r.retry_count,
            "job_title": r.job_title,
            "company": r.company,
            "source_portal": r.source_portal,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/send-logs/funnel")
async def admin_send_logs_funnel(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    candidate_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
):
    """Email funnel stats: send counts by status with computed rates."""
    from services.api.models.db import SendLog
    from sqlalchemy import func as sa_func, text as sa_text
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    conditions = [SendLog.sent_at >= since]
    if candidate_id:
        conditions.append(SendLog.candidate_id == candidate_id)

    q = select(SendLog.status, sa_func.count(SendLog.id).label("cnt"))
    for c in conditions:
        q = q.where(c)
    q = q.group_by(SendLog.status)

    rows = (await db.execute(q)).fetchall()
    counts = {row[0]: row[1] for row in rows}

    total = sum(counts.values())
    sent = counts.get("sent", 0) + counts.get("delivered", 0) + counts.get("opened", 0) + counts.get("clicked", 0)
    delivered = counts.get("delivered", 0) + counts.get("opened", 0) + counts.get("clicked", 0)
    opened = counts.get("opened", 0) + counts.get("clicked", 0)
    clicked = counts.get("clicked", 0)
    bounced = counts.get("bounced", 0) + counts.get("soft_bounced", 0)

    return {
        "period_days": days,
        "total": total,
        "by_status": counts,
        "funnel": {
            "queued": counts.get("queued", 0),
            "sent": sent,
            "delivered": delivered,
            "opened": opened,
            "clicked": clicked,
            "bounced": bounced,
        },
        "rates": {
            "delivery_rate": round(delivered / max(sent, 1) * 100, 1),
            "open_rate": round(opened / max(delivered, 1) * 100, 1),
            "click_rate": round(clicked / max(opened, 1) * 100, 1),
            "bounce_rate": round(bounced / max(sent, 1) * 100, 1),
        },
    }


@router.get("/send-logs/delivery-report")
async def admin_send_logs_delivery_report(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    days: int = Query(14, ge=1, le=90),
):
    """Daily email delivery breakdown by provider and status for the last N days."""
    from sqlalchemy import text as sa_text
    from datetime import datetime, timedelta, timezone

    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    r = await db.execute(sa_text("""
        SELECT
            DATE(sent_at) AS day,
            provider,
            status,
            COUNT(*) AS cnt
        FROM send_logs
        WHERE sent_at >= :since
        GROUP BY 1, 2, 3
        ORDER BY 1 DESC, 4 DESC
    """), {"since": since})
    rows = r.fetchall()
    items = [
        {"day": str(row[0]), "provider": row[1], "status": row[2], "count": row[3]}
        for row in rows
    ]
    return {"period_days": days, "items": items, "rows": len(items)}
