"""Redis-backed sliding-window rate limiter for Groq API calls.

All workers share a single counter in Redis so the RPM cap is enforced
globally across every process, not just within one Celery worker.

Usage (async):
    from services.ai.rate_limiter import wait_for_groq_slot, get_least_used_key

    key_id = await get_least_used_key()
    acquired = await wait_for_groq_slot(key_id)   # sleeps until slot available
    if not acquired:
        raise RuntimeError("rate limit wait exceeded")
    response = await groq_llm.ainvoke(...)
"""
from __future__ import annotations

import asyncio
import random
import time

import structlog

logger = structlog.get_logger(__name__)

# Atomic sliding-window check + acquire via Lua (runs as a single Redis command).
# KEYS[1] = sorted-set key  (e.g. "rl:groq:default:rpm")
# ARGV[1] = now_ms           (current timestamp, milliseconds)
# ARGV[2] = window_ms        (60 000 for 1-minute window)
# ARGV[3] = limit            (e.g. 10)
# ARGV[4] = unique member    (prevents duplicate score collisions)
#
# Returns [1, new_count]          if slot acquired
#         [0, oldest_score_str]   if rate-limited (oldest_score in ms → use to compute retry_after)
_ACQUIRE_LUA = """
local key    = KEYS[1]
local now    = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit  = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window / 1000) + 2)
    return {1, count + 1}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if #oldest > 0 then
        return {0, oldest[2]}
    end
    return {0, tostring(now)}
end
"""


async def _get_redis():
    from services.api.core.cache import get_redis
    return await get_redis()


async def acquire_groq_slot(key_id: str = "default") -> tuple[bool, float]:
    """Try to claim one Groq RPM slot for the given API key.

    Returns:
        (True, 0.0)         — slot acquired, proceed immediately
        (False, retry_secs) — rate-limited; caller should wait retry_secs then retry
        (True, 0.0)         — Redis unavailable (fail-open)
    """
    from services.api.core.config import get_settings
    settings = get_settings()
    rpm: int = getattr(settings, "groq_rpm", 10)

    r = await _get_redis()
    if r is None:
        return True, 0.0

    try:
        redis_key = f"rl:groq:{key_id}:rpm"
        now_ms = int(time.time() * 1000)
        window_ms = 60_000
        # Unique member prevents score collisions when two calls land in the same ms
        member = f"{now_ms}-{random.randint(0, 999_999)}"

        script = r.register_script(_ACQUIRE_LUA)
        result = await script(keys=[redis_key], args=[now_ms, window_ms, rpm, member])

        if int(result[0]) == 1:
            return True, 0.0

        # Rate-limited: compute how long until the oldest slot expires
        oldest_ms = float(result[1])
        retry_after = max(1.0, (oldest_ms + window_ms - now_ms) / 1000.0)
        logger.debug("groq_slot_unavailable", key_id=key_id, retry_after_s=round(retry_after, 1))
        return False, retry_after

    except Exception as exc:
        logger.warning("rate_limiter_error", error=str(exc)[:200])
        return True, 0.0  # fail-open


async def wait_for_groq_slot(key_id: str = "default", max_wait: float = 180.0) -> bool:
    """Block (via asyncio.sleep) until a Groq slot is available or max_wait is hit.

    Adds per-coroutine jitter (0–2 s) to prevent thundering herd when many
    asyncio.gather coroutines all wake up after the same sleep.

    Returns True if a slot was acquired, False if max_wait was exceeded.
    """
    waited = 0.0
    attempts = 0
    while waited < max_wait:
        acquired, retry_after = await acquire_groq_slot(key_id)
        if acquired:
            if attempts > 0:
                logger.debug("groq_slot_acquired_after_wait", waited_s=round(waited, 1))
            return True
        jitter = random.uniform(0.2, 2.0)
        sleep_for = min(retry_after + jitter, max_wait - waited)
        if sleep_for <= 0:
            break
        await asyncio.sleep(sleep_for)
        waited += sleep_for
        attempts += 1
    logger.warning("groq_slot_wait_exceeded", key_id=key_id, max_wait=max_wait)
    return False


async def get_least_used_key() -> str:
    """Return the Groq key ID with the most remaining capacity in the current window.

    Reads GROQ_API_KEYS (comma-separated list of key identifiers, NOT the raw
    keys themselves — use short aliases like "key1,key2").  Falls back to
    "default" when the setting is absent or Redis is unavailable.
    """
    from services.api.core.config import get_settings
    settings = get_settings()

    raw: str = getattr(settings, "groq_api_keys", "") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()] or ["default"]

    if len(keys) == 1:
        return keys[0]

    r = await _get_redis()
    if r is None:
        return keys[0]

    try:
        now_ms = int(time.time() * 1000)
        window_ms = 60_000
        best_key, best_count = keys[0], float("inf")
        for kid in keys:
            rkey = f"rl:groq:{kid}:rpm"
            await r.zremrangebyscore(rkey, 0, now_ms - window_ms)
            count = await r.zcard(rkey)
            if count < best_count:
                best_key, best_count = kid, count
        return best_key
    except Exception:
        return keys[0]


async def get_groq_rate_status() -> dict:
    """Return current usage for all configured keys — used by admin endpoints."""
    from services.api.core.config import get_settings
    settings = get_settings()

    raw: str = getattr(settings, "groq_api_keys", "") or ""
    keys = [k.strip() for k in raw.split(",") if k.strip()] or ["default"]
    rpm: int = getattr(settings, "groq_rpm", 10)

    r = await _get_redis()
    if r is None:
        return {"available": True, "redis_unavailable": True}

    status = {}
    now_ms = int(time.time() * 1000)
    window_ms = 60_000
    try:
        for kid in keys:
            rkey = f"rl:groq:{kid}:rpm"
            await r.zremrangebyscore(rkey, 0, now_ms - window_ms)
            used = await r.zcard(rkey)
            status[kid] = {"used": used, "limit": rpm, "remaining": max(0, rpm - used)}
    except Exception as exc:
        return {"error": str(exc)[:200]}
    return status
