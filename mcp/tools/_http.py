import json
import time
import asyncio
from typing import Any

import httpx

from config import (
    API_URL,
    API_KEY,
    HTTP_TIMEOUT_QUICK,
    HTTP_TIMEOUT_NORMAL,
    HTTP_TIMEOUT_LONG,
    HTTP_MAX_RETRIES,
    HTTP_RETRY_BACKOFF,
    CACHE_TTL_DEFAULT,
    CACHE_MAX_ENTRIES,
    logger,
)

_REDACT_KEYS = frozenset({
    "key", "password", "secret", "token", "apikey", "api_key",
    "authorization", "cookie", "session", "credential",
})

_cache: dict[str, tuple[float, Any]] = {}
_cache_order: list[str] = []


def _redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {
            k: "***REDACTED***" if k.lower() in _REDACT_KEYS else _redact(v)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i) for i in obj]
    return obj


def _cache_get(path: str, ttl: int) -> tuple[bool, Any]:
    if path in _cache:
        ts, data = _cache[path]
        if time.monotonic() - ts < ttl:
            return True, data
        del _cache[path]
    return False, None


def _cache_set(path: str, data: Any) -> None:
    if len(_cache_order) >= CACHE_MAX_ENTRIES:
        oldest = _cache_order.pop(0)
        _cache.pop(oldest, None)
    _cache[path] = (time.monotonic(), data)
    _cache_order.append(path)


def _cache_invalidate(path: str = "", prefix: str = "") -> int:
    count = 0
    keys_to_remove = []
    for k in list(_cache.keys()):
        if (path and k == path) or (prefix and k.startswith(prefix)):
            keys_to_remove.append(k)
            count += 1
    for k in keys_to_remove:
        _cache.pop(k, None)
        if k in _cache_order:
            _cache_order.remove(k)
    return count


def _resolve_timeout(timeout: str | int | None) -> float:
    if timeout is None:
        return HTTP_TIMEOUT_NORMAL
    if isinstance(timeout, (int, float)):
        return float(timeout)
    mapping = {
        "quick": HTTP_TIMEOUT_QUICK,
        "normal": HTTP_TIMEOUT_NORMAL,
        "long": HTTP_TIMEOUT_LONG,
    }
    return float(mapping.get(timeout, HTTP_TIMEOUT_NORMAL))


async def api(
    method: str,
    path: str,
    *,
    timeout: str | int | None = None,
    cache_ttl: int = 0,
    invalidate_cache: bool = False,
    **kwargs: Any,
) -> dict | list:
    headers = {"X-API-Key": API_KEY}
    url = f"{API_URL}{path}"

    if invalidate_cache:
        _cache_invalidate(prefix=path)

    if method.upper() == "GET" and cache_ttl > 0:
        cache_key = f"{method}:{path}:{json.dumps(kwargs, sort_keys=True, default=str)}"
        hit, cached = _cache_get(cache_key, cache_ttl)
        if hit:
            logger.debug("cache_hit %s", path)
            return cached

    last_exc: Exception | None = None
    resolved_timeout = _resolve_timeout(timeout)

    for attempt in range(HTTP_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=resolved_timeout) as client:
                start = time.monotonic()
                r = await client.request(method, url, headers=headers, **kwargs)
                elapsed = time.monotonic() - start
                r.raise_for_status()
                data = _redact(r.json())
                logger.debug(
                    "api_call %s %s %.0fms attempt=%d",
                    method, path, elapsed * 1000, attempt + 1,
                )
                if method.upper() == "GET" and cache_ttl > 0:
                    _cache_set(cache_key, data)
                return data
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise
            last_exc = exc
            logger.warning(
                "api_retry %s %s status=%d attempt=%d/%d",
                method, path, exc.response.status_code,
                attempt + 1, HTTP_MAX_RETRIES,
            )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            last_exc = exc
            logger.warning(
                "api_retry %s %s error=%s attempt=%d/%d",
                method, path, type(exc).__name__,
                attempt + 1, HTTP_MAX_RETRIES,
            )

        if attempt < HTTP_MAX_RETRIES - 1:
            delay = HTTP_RETRY_BACKOFF * (2 ** attempt)
            await asyncio.sleep(delay)

    raise last_exc or httpx.ConnectError(f"All {HTTP_MAX_RETRIES} retries failed for {path}")


def fmt(data: Any) -> str:
    return json.dumps(data, indent=2, default=str)
