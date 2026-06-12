"""Lightweight per-IP rate limiting for abuse-prone endpoints.

Redis fixed-window counter (INCR + EXPIRE), fail-open when Redis is
unavailable — consistent with the cache helpers' behaviour. Intended for
low-volume endpoints (auth); not a general API throttle.
"""
from __future__ import annotations

import structlog
from fastapi import HTTPException, Request

from services.api.core.cache import get_redis

logger = structlog.get_logger(__name__)


def _client_ip(request: Request) -> str:
    # Behind the Cloudflare tunnel / nginx the original client is the first
    # entry in X-Forwarded-For; fall back to the socket peer for direct hits.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(scope: str, max_requests: int, window_seconds: int):
    """Dependency factory: at most `max_requests` per IP per window."""

    async def _check(request: Request) -> None:
        r = await get_redis()
        if r is None:
            return  # fail-open, matching cache helpers
        key = f"rl:{scope}:{_client_ip(request)}"
        try:
            count = await r.incr(key)
            if count == 1:
                await r.expire(key, window_seconds)
            if count > max_requests:
                ttl = await r.ttl(key)
                raise HTTPException(
                    status_code=429,
                    detail="Too many attempts. Try again later.",
                    headers={"Retry-After": str(max(ttl, 1))},
                )
        except HTTPException:
            raise
        except Exception as exc:
            logger.debug("rate_limit_redis_error", scope=scope, error=str(exc))

    return _check
