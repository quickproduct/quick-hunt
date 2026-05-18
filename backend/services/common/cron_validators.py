"""Cron job validation decorators for Celery tasks.

Provides protection against:
- Overlapping executions (singleton lock)
- Rate limiting (max runs per window)
- Queue overflow (queue depth checks)
- Cascading failures (circuit breaker)
- Runaway tasks (max runtime tracking)
"""

import asyncio
import functools
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

import structlog

logger = structlog.get_logger(__name__)

# Global thread pool for running sync functions that use run_async internally
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="cron_validator")


def _run_in_new_thread_with_loop(func, *args, **kwargs):
    """Run a function in a new thread with its own isolated event loop.
    
    This prevents nested event loop conflicts when the wrapped function
    internally uses run_async() which tries to call run_until_complete().
    """
    import threading
    from services.common.async_utils import _loop_local
    result = None
    exception = None
    
    def target():
        nonlocal result, exception
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            _loop_local.loop = loop
            try:
                result = func(*args, **kwargs)
            finally:
                _loop_local.loop = None
                loop.close()
                # The task may have called get_redis() and stored a client bound
                # to this thread's now-closed loop. Clear it so the next caller
                # on the main event loop creates a fresh connection.
                try:
                    import services.api.core.cache as _cache
                    _cache._redis_client = None
                except Exception:
                    pass
        except Exception as e:
            exception = e
    
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(timeout=1800)  # 30 min timeout — large batches (e.g. 200 HR email lookups) need headroom

    if thread.is_alive():
        raise TimeoutError("Task execution timed out after 1800s")
    if exception:
        raise exception
    return result

# ── Redis Key Prefixes ────────────────────────────────────────────────────────
_LOCK_PREFIX = "cron:lock:"
_RATE_PREFIX = "cron:rate:"
_CIRCUIT_PREFIX = "cron:circuit:"
_LAST_RUN_PREFIX = "cron:last_run:"


async def _get_redis_conn():
    """Get Redis connection for validation operations.
    
    Reuses the shared connection from the API cache module to avoid
    creating a new connection per call.
    """
    try:
        from services.api.core.cache import get_redis
        return await get_redis()
    except Exception as exc:
        logger.warning("cron_validator_redis_failed", error=str(exc))
        return None


class CronValidationError(Exception):
    """Raised when a cron validation check fails."""

    pass


class CircuitBreakerOpen(CronValidationError):
    """Raised when circuit breaker is open (too many failures)."""

    pass


class QueueOverflow(CronValidationError):
    """Raised when destination queue has too many pending tasks."""

    pass


class SingletonLockHeld(CronValidationError):
    """Raised when another instance of this task is already running."""

    pass


class RateLimitExceeded(CronValidationError):
    """Raised when rate limit for this task is exceeded."""

    pass


def _get_queue_for_task(task_name: str) -> Optional[str]:
    """Map task name to its Celery queue."""
    from services.scraper.celery_app import celery_app

    route = celery_app.amqp.router.route({}, task_name)
    queue = route.get("queue", "celery")
    # Celery may return a kombu Queue object instead of a string — extract
    # the queue name to avoid passing ``<unbound Queue celery -> …>`` into
    # the RabbitMQ Management API URL (causes 404s).
    if hasattr(queue, "name"):
        queue = queue.name
    return str(queue)


async def _check_queue_depth(queue_name: str, max_depth: int) -> bool:
    """Check if queue has fewer than max_depth pending messages.

    Queries the correct broker based on configuration:
    - RabbitMQ: uses Management API (http://{host}:15672/api/queues)
    - Redis: uses LLEN on the queue key
    """
    try:
        from services.api.core.config import get_settings
        settings = get_settings()

        # ── RabbitMQ Management API ──────────────────────────────────────
        rabbit_url = settings.rabbitmq_url
        if rabbit_url and rabbit_url.startswith(("amqp://", "amqps://")):
            depth = await _get_rabbitmq_queue_depth(rabbit_url, queue_name)
            if depth is not None:
                return depth < max_depth
            # Fall through to Redis check if RabbitMQ API query failed

        # ── Redis broker fallback ────────────────────────────────────────
        redis = await _get_redis_conn()
        if not redis:
            return True  # Fail open if both brokers unavailable

        queue_key = queue_name if queue_name != "celery" else "celery"
        depth = await redis.llen(queue_key)
        return depth < max_depth
    except Exception as exc:
        logger.warning("queue_depth_check_failed", queue=queue_name, error=str(exc))
        return True  # Fail open


async def _get_rabbitmq_queue_depth(rabbit_url: str, queue_name: str) -> int | None:
    """Query RabbitMQ Management API for queue message count.

    Returns the number of messages (ready + unacked), or None on failure.
    Works with both local Docker RabbitMQ and CloudAMQP.
    """
    import httpx
    from urllib.parse import urlparse, unquote

    try:
        parsed = urlparse(rabbit_url)
        host = parsed.hostname or "rabbitmq"
        port = parsed.port or 5672
        user = unquote(parsed.username or "guest")
        password = unquote(parsed.password or "guest")
        vhost = unquote(parsed.path.lstrip("/")) or "/"

        # Management API is on port 15672 (local) or 443 (CloudAMQP)
        mgmt_port = 15672
        if rabbit_url.startswith("amqps://"):
            # CloudAMQP: management API is on the same host, port 443
            mgmt_scheme = "https"
            mgmt_port = 443
        else:
            mgmt_scheme = "http"

        # URL-encode the vhost for the API path (%2F for /)
        from urllib.parse import quote
        vhost_encoded = quote(vhost, safe="")

        mgmt_url = f"{mgmt_scheme}://{host}:{mgmt_port}/api/queues/{vhost_encoded}/{queue_name}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(mgmt_url, auth=(user, password))
            if resp.status_code == 200:
                data = resp.json()
                depth = data.get("messages", 0) or 0
                logger.debug(
                    "rabbitmq_queue_depth",
                    queue=queue_name,
                    depth=depth,
                    ready=data.get("messages_ready", 0),
                    unacked=data.get("messages_unacknowledged", 0),
                )
                return depth
            else:
                # 404 is expected when queue doesn't exist yet - will fall back to Redis
                if resp.status_code == 404:
                    logger.debug(
                        "rabbitmq_queue_not_found",
                        queue=queue_name,
                        status=resp.status_code,
                        info="Queue may not exist yet, falling back to Redis",
                    )
                else:
                    logger.warning(
                        "rabbitmq_api_error",
                        queue=queue_name,
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                return None
    except Exception as exc:
        logger.warning("rabbitmq_queue_depth_failed", queue=queue_name, error=str(exc))
        return None


async def _acquire_lock(lock_key: str, ttl_seconds: int) -> bool:
    """Try to acquire a distributed lock via Redis SET NX."""
    redis = await _get_redis_conn()
    if not redis:
        return True  # Fail open if Redis unavailable

    try:
        acquired = await redis.set(lock_key, str(time.time()), nx=True, ex=ttl_seconds)
        return acquired
    except Exception as exc:
        logger.warning("lock_acquire_failed", key=lock_key, error=str(exc))
        return True  # Fail open


async def _release_lock(lock_key: str) -> None:
    """Release a distributed lock."""
    redis = await _get_redis_conn()
    if not redis:
        return

    try:
        await redis.delete(lock_key)
    except Exception as exc:
        logger.warning("lock_release_failed", key=lock_key, error=str(exc))


async def _check_rate_limit(rate_key: str, max_runs: int, window_seconds: int) -> bool:
    """Check if rate limit is exceeded using sliding window."""
    redis = await _get_redis_conn()
    if not redis:
        return True  # Fail open

    try:
        now = time.time()
        window_start = now - window_seconds

        # Remove old entries outside window
        await redis.zremrangebyscore(rate_key, 0, window_start)

        # Count current entries
        current_count = await redis.zcard(rate_key)
        if current_count >= max_runs:
            return False

        # Add current run
        await redis.zadd(rate_key, {str(now): now})
        await redis.expire(rate_key, window_seconds)
        return True
    except Exception as exc:
        logger.warning("rate_limit_check_failed", key=rate_key, error=str(exc))
        return True  # Fail open


async def _check_circuit_breaker(circuit_key: str, failure_threshold: int, recovery_seconds: int) -> bool:
    """Check if circuit breaker is open (too many recent failures)."""
    redis = await _get_redis_conn()
    if not redis:
        return True  # Fail open

    try:
        # Check if circuit is open
        state = await redis.get(f"{circuit_key}:state")
        if state == "open":
            # Check if recovery time has passed
            opened_at = await redis.get(f"{circuit_key}:opened_at")
            if opened_at:
                opened_time = float(opened_at)
                if time.time() - opened_time > recovery_seconds:
                    # Move to half-open
                    await redis.set(f"{circuit_key}:state", "half_open", ex=recovery_seconds)
                    await redis.delete(f"{circuit_key}:failures")
                    return True
            return False  # Circuit still open

        # Circuit is closed or half-open, allow through
        return True
    except Exception as exc:
        logger.warning("circuit_check_failed", key=circuit_key, error=str(exc))
        return True  # Fail open


async def _record_failure(circuit_key: str, failure_threshold: int, recovery_seconds: int) -> None:
    """Record a failure for circuit breaker tracking."""
    redis = await _get_redis_conn()
    if not redis:
        return

    try:
        failures_key = f"{circuit_key}:failures"
        now = time.time()

        # Add failure timestamp
        await redis.zadd(failures_key, {str(now): now})
        await redis.expire(failures_key, recovery_seconds * 2)

        # Clean old failures
        await redis.zremrangebyscore(failures_key, 0, now - recovery_seconds)

        # Check threshold
        count = await redis.zcard(failures_key)
        if count >= failure_threshold:
            await redis.set(f"{circuit_key}:state", "open", ex=recovery_seconds * 2)
            await redis.set(f"{circuit_key}:opened_at", str(now), ex=recovery_seconds * 2)
            logger.warning("circuit_breaker_opened", key=circuit_key, failures=count)
    except Exception as exc:
        logger.warning("record_failure_failed", key=circuit_key, error=str(exc))


async def _record_success(circuit_key: str) -> None:
    """Record a success, potentially closing the circuit."""
    redis = await _get_redis_conn()
    if not redis:
        return

    try:
        state = await redis.get(f"{circuit_key}:state")
        if state == "half_open":
            # Success in half-open, close the circuit
            await redis.delete(f"{circuit_key}:state")
            await redis.delete(f"{circuit_key}:failures")
            await redis.delete(f"{circuit_key}:opened_at")
            logger.info("circuit_breaker_closed", key=circuit_key)
    except Exception as exc:
        logger.warning("record_success_failed", key=circuit_key, error=str(exc))


async def _track_run_time(task_name: str, start_time: float) -> None:
    """Track task execution time for monitoring."""
    duration = time.time() - start_time
    redis = await _get_redis_conn()
    if redis:
        try:
            await redis.hset(
                f"{_LAST_RUN_PREFIX}{task_name}",
                mapping={
                    "last_run": str(datetime.now(timezone.utc)),
                    "duration": str(duration),
                    "timestamp": str(start_time),
                },
            )
            await redis.expire(f"{_LAST_RUN_PREFIX}{task_name}", 86400 * 7)  # Keep 7 days
        except Exception:
            pass

    logger.info("cron_task_completed", task=task_name, duration_seconds=round(duration, 2))


def cron_safe(
    task_name: Optional[str] = None,
    singleton_ttl_seconds: int = 3600,
    max_runs_per_hour: int = 12,
    max_queue_depth: int = 1000,
    circuit_failure_threshold: int = 5,
    circuit_recovery_seconds: int = 1800,
    log_skipped: bool = True,
):
    """Decorator that wraps a Celery task with comprehensive cron validation.

    Args:
        task_name: Unique task identifier (defaults to function name)
        singleton_ttl_seconds: Lock TTL to prevent overlapping runs (default 1h)
        max_runs_per_hour: Max executions allowed per hour
        max_queue_depth: Abort if destination queue exceeds this many pending tasks
        circuit_failure_threshold: Open circuit after this many failures
        circuit_recovery_seconds: Wait this long before trying again after circuit opens
        log_skipped: Whether to log when task is skipped due to validation

    Raises:
        SingletonLockHeld: If another instance is still running
        RateLimitExceeded: If rate limit hit
        QueueOverflow: If destination queue is overwhelmed
        CircuitBreakerOpen: If circuit is open due to failures
    """

    def decorator(func: Callable) -> Callable:
        nonlocal task_name
        if task_name is None:
            task_name = func.__name__

        lock_key = f"{_LOCK_PREFIX}{task_name}"
        rate_key = f"{_RATE_PREFIX}{task_name}"
        circuit_key = f"{_CIRCUIT_PREFIX}{task_name}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            from services.common.async_utils import run_async

            start_time = time.time()
            run_id = f"{task_name}:{start_time}"

            async def validate_and_run():
                # 1. Check circuit breaker
                circuit_ok = await _check_circuit_breaker(
                    circuit_key, circuit_failure_threshold, circuit_recovery_seconds
                )
                if not circuit_ok:
                    msg = f"Circuit breaker OPEN for {task_name}"
                    if log_skipped:
                        logger.warning("cron_skipped_circuit_open", task=task_name)
                    raise CircuitBreakerOpen(msg)

                # 2. Check singleton lock
                lock_acquired = await _acquire_lock(lock_key, singleton_ttl_seconds)
                if not lock_acquired:
                    msg = f"Singleton lock held for {task_name} - previous run still active"
                    if log_skipped:
                        logger.warning("cron_skipped_lock_held", task=task_name)
                    raise SingletonLockHeld(msg)

                try:
                    # 3. Check rate limit
                    rate_ok = await _check_rate_limit(rate_key, max_runs_per_hour, 3600)
                    if not rate_ok:
                        msg = f"Rate limit exceeded for {task_name} ({max_runs_per_hour}/hour)"
                        if log_skipped:
                            logger.warning("cron_skipped_rate_limit", task=task_name, limit=max_runs_per_hour)
                        raise RateLimitExceeded(msg)

                    # 4. Check queue depth
                    queue_name = _get_queue_for_task(task_name)
                    queue_ok = await _check_queue_depth(queue_name, max_queue_depth)
                    if not queue_ok:
                        msg = f"Queue '{queue_name}' has >{max_queue_depth} pending tasks"
                        if log_skipped:
                            logger.warning("cron_skipped_queue_overflow", task=task_name, queue=queue_name, max_depth=max_queue_depth)
                        raise QueueOverflow(msg)

                    # All validations passed - run the task
                    logger.info("cron_task_started", task=task_name, run_id=run_id, queue=queue_name)

                    try:
                        if asyncio.iscoroutinefunction(func):
                            result = await func(*args, **kwargs)
                        else:
                            # Run sync function in a dedicated thread with its own
                            # fresh event loop. Using a new thread (not a reused
                            # ThreadPoolExecutor thread) guarantees the asyncpg
                            # connection pool in the task's _run_async() always runs
                            # on the loop it was created for, preventing SIGSEGV from
                            # cross-loop connection reuse.
                            result = await asyncio.get_running_loop().run_in_executor(
                                _executor,
                                functools.partial(_run_in_new_thread_with_loop, func, *args, **kwargs)
                            )
                        await _record_success(circuit_key)
                        await _track_run_time(task_name, start_time)
                        return result
                    except Exception as exc:
                        await _record_failure(circuit_key, circuit_failure_threshold, circuit_recovery_seconds)
                        raise

                finally:
                    await _release_lock(lock_key)

            try:
                import asyncio
                return run_async(validate_and_run())
            except CronValidationError as exc:
                # Lock held / rate limit / circuit open — expected skip.
                # Return a result (not raise) so Celery marks the task as
                # succeeded and does NOT retry it.
                return {"skipped": True, "reason": str(exc)}
            except Exception as exc:
                logger.error("cron_task_failed", task=task_name, run_id=run_id, error=str(exc))
                raise

        return wrapper

    return decorator


def get_cron_stats(task_name: str) -> dict:
    """Get current validation stats for a cron task."""
    from services.common.async_utils import run_async

    async def _fetch():
        redis = await _get_redis_conn()
        if not redis:
            return {"error": "Redis unavailable"}

        lock_key = f"{_LOCK_PREFIX}{task_name}"
        rate_key = f"{_RATE_PREFIX}{task_name}"
        circuit_key = f"{_CIRCUIT_PREFIX}{task_name}"
        last_run_key = f"{_LAST_RUN_PREFIX}{task_name}"

        try:
            lock_ttl = await redis.ttl(lock_key)
            rate_count = await redis.zcard(rate_key)
            circuit_state = await redis.get(f"{circuit_key}:state") or "closed"
            failures = await redis.zcard(f"{circuit_key}:failures") if circuit_state != "closed" else 0
            last_run = await redis.hgetall(last_run_key)

            return {
                "task": task_name,
                "lock_active": lock_ttl > 0,
                "lock_ttl_seconds": lock_ttl if lock_ttl > 0 else 0,
                "runs_last_hour": rate_count,
                "circuit_state": circuit_state,
                "recent_failures": failures,
                "last_run": last_run,
            }
        except Exception as exc:
            return {"error": str(exc)}

    return run_async(_fetch())


def reset_circuit_breaker(task_name: str) -> bool:
    """Manually reset a circuit breaker. Returns True if successful."""
    from services.common.async_utils import run_async

    async def _reset():
        redis = await _get_redis_conn()
        if not redis:
            return False

        circuit_key = f"{_CIRCUIT_PREFIX}{task_name}"
        try:
            await redis.delete(f"{circuit_key}:state")
            await redis.delete(f"{circuit_key}:failures")
            await redis.delete(f"{circuit_key}:opened_at")
            logger.info("circuit_breaker_reset", task=task_name)
            return True
        except Exception as exc:
            logger.error("circuit_reset_failed", task=task_name, error=str(exc))
            return False

    return run_async(_reset())
