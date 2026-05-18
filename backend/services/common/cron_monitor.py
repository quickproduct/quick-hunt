"""@cron_monitored decorator — records every cron/beat task run in CronRun table.

Usage in a task file:
    from services.common.cron_monitor import cron_monitored

    @celery_app.task(name="services.scraper.tasks.my_task")
    @cron_safe(task_name="my_task", ...)
    @cron_monitored("my_task")
    def my_task() -> dict:
        ...

The decorator:
  - Creates a CronRun row before execution (status="running")
  - Updates it on completion with status, duration, result, and any error
  - Mirrors live state to Redis (TTL 2 h) for the SSE stream at /admin/cron/live
  - Fails silently if DB / Redis is unavailable so the underlying task is unaffected
"""
from __future__ import annotations

import socket
import traceback as _tb
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable

import structlog

logger = structlog.get_logger(__name__)

_REDIS_RUN_PREFIX = "cron:run:"
_REDIS_RUN_TTL = 7200  # 2 h — keeps live entries warm for the SSE stream


# ── async helpers (run inside worker event loop via run_async) ────────────────

async def _start_run_async(task_name: str, triggered_by: str, celery_task_id: str | None = None) -> str:
    """Insert a CronRun row and mirror it to Redis.  Returns run_id."""
    import uuid
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import CronRun
    from services.api.core.cache import get_redis

    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    host = socket.gethostname()

    try:
        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            run = CronRun(
                id=run_id,
                task_name=task_name,
                celery_task_id=celery_task_id,
                started_at=now,
                status="running",
                triggered_by=triggered_by,
                worker_host=host,
            )
            session.add(run)
            await session.commit()
    except Exception as exc:
        logger.warning("cron_monitor_start_db_error", task=task_name, error=str(exc)[:200])

    try:
        r = await get_redis()
        if r:
            await r.hset(f"{_REDIS_RUN_PREFIX}{run_id}", mapping={
                "task_name": task_name,
                "celery_task_id": celery_task_id or "",
                "status": "running",
                "started_at": now.isoformat(),
                "triggered_by": triggered_by,
                "worker_host": host,
            })
            await r.expire(f"{_REDIS_RUN_PREFIX}{run_id}", _REDIS_RUN_TTL)
    except Exception as exc:
        logger.debug("cron_monitor_start_redis_error", error=str(exc)[:200])

    return run_id


async def _finish_run_async(
    run_id: str,
    task_name: str,
    started_at: datetime,
    status: str,
    post_state: Any = None,
    error: str | None = None,
    traceback_str: str | None = None,
    steps: list | None = None,
) -> None:
    """Update the CronRun row and Redis hash on task completion."""
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import CronRun
    from services.api.core.cache import get_redis

    ended_at = datetime.now(timezone.utc)
    duration_ms = int((ended_at - started_at).total_seconds() * 1000)

    try:
        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            run = await session.get(CronRun, run_id)
            if run:
                run.ended_at = ended_at
                run.duration_ms = duration_ms
                run.status = status
                run.error_summary = (error or "")[:500] or None
                run.error_traceback = traceback_str
                run.post_state = post_state if isinstance(post_state, dict) else None
                run.steps = steps or []
                await session.commit()
    except Exception as exc:
        logger.warning("cron_monitor_finish_db_error", run_id=run_id, error=str(exc)[:200])

    try:
        r = await get_redis()
        if r:
            await r.hset(f"{_REDIS_RUN_PREFIX}{run_id}", mapping={
                "status": status,
                "ended_at": ended_at.isoformat(),
                "duration_ms": duration_ms,
                "error_summary": error or "",
            })
            await r.expire(f"{_REDIS_RUN_PREFIX}{run_id}", _REDIS_RUN_TTL)
    except Exception as exc:
        logger.debug("cron_monitor_finish_redis_error", error=str(exc)[:200])


# ── public decorator ──────────────────────────────────────────────────────────

def cron_monitored(task_name: str, triggered_by: str = "beat") -> Callable:
    """Wrap a synchronous Celery task to persist CronRun history.

    Must be applied AFTER @cron_safe (closer to the function body) so that
    @cron_safe's skip/guard logic is visible as the returned result.

    Example stack (outermost → innermost):
        @celery_app.task(...)
        @cron_safe(...)
        @cron_monitored("my_task")      ← this decorator
        def my_task(): ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            from services.common.async_utils import run_async

            started_at = datetime.now(timezone.utc)

            # Start the run record — fail silently if infra is down
            try:
                celery_task_id = None
                try:
                    from celery import current_task
                    request = getattr(current_task, "request", None)
                    celery_task_id = getattr(request, "id", None)
                except Exception:
                    celery_task_id = None
                run_id = run_async(_start_run_async(task_name, triggered_by, celery_task_id))
            except Exception as exc:
                logger.debug("cron_monitor_start_failed", task=task_name, error=str(exc)[:200])
                run_id = None

            status = "success"
            result: Any = None
            error_msg: str | None = None
            traceback_str: str | None = None

            try:
                result = func(*args, **kwargs)
                if isinstance(result, dict) and result.get("skipped") is True:
                    status = "skipped"
                return result
            except Exception as exc:
                status = "failure"
                error_msg = str(exc)[:500]
                traceback_str = _tb.format_exc()[:5000]
                raise
            finally:
                if run_id:
                    try:
                        run_async(_finish_run_async(
                            run_id=run_id,
                            task_name=task_name,
                            started_at=started_at,
                            status=status,
                            post_state=result if isinstance(result, dict) else None,
                            error=error_msg,
                            traceback_str=traceback_str,
                        ))
                    except Exception as exc:
                        logger.debug("cron_monitor_finish_failed", error=str(exc)[:200])

        return wrapper
    return decorator
