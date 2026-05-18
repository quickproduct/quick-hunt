"""Lightweight Redis cache helpers for the FastAPI layer.

Usage:
    from services.api.core.cache import get_redis, cache_get, cache_set, cache_delete

All functions are async-safe and fail-open: any Redis error is logged and
treated as a cache miss so the API continues to work without Redis.
"""
import json
import ssl
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_redis_client = None


async def get_redis():
    """Return a shared aioredis client, lazily initialised."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis.asyncio as aioredis  # redis>=4.2 ships this

        from services.api.core.config import get_settings

        settings = get_settings()
        url = settings.redis_url
        # Upstash uses rediss:// (TLS) but with CERT_NONE — same as the Celery
        # broker config in celery_app.py. Using create_default_context() would
        # require valid certs and cause "SSL: CERTIFICATE_VERIFY_FAILED" errors.
        ssl_ctx: ssl.SSLContext | None = None
        if url.startswith("rediss://"):
            ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE
        kwargs = {
            "encoding": "utf-8",
            "decode_responses": True,
            "socket_timeout": 3,
            "socket_connect_timeout": 3,
        }
        if ssl_ctx is not None:
            kwargs["ssl_context"] = ssl_ctx
        _redis_client = aioredis.from_url(url, **kwargs)
    except Exception as exc:
        logger.warning("redis_init_failed", error=str(exc))
        _redis_client = None
    return _redis_client


async def cache_get(key: str) -> Any | None:
    """Return cached value (deserialised JSON) or None on miss / error."""
    try:
        r = await get_redis()
        if r is None:
            return None
        raw = await r.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("cache_get_error", key=key, error=str(exc))
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int = 60) -> None:
    """Serialise value as JSON and store it with an expiry. Fails silently."""
    try:
        r = await get_redis()
        if r is None:
            return
        await r.set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        logger.debug("cache_set_error", key=key, error=str(exc))


async def cache_delete(key: str) -> None:
    """Delete a cache key. Fails silently."""
    try:
        r = await get_redis()
        if r is None:
            return
        await r.delete(key)
    except Exception as exc:
        logger.debug("cache_delete_error", key=key, error=str(exc))
