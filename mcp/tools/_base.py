import json
import time
import functools
from datetime import datetime, timezone
from typing import Any, Callable

from config import logger


def ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def tool_error(tool: str, error: str, suggestion: str = "") -> str:
    payload: dict[str, Any] = {
        "error": error,
        "tool": tool,
        "timestamp": ts(),
    }
    if suggestion:
        payload["suggestion"] = suggestion
    return json.dumps(payload, indent=2)


def tool_result(tool: str, data: Any, **extra: Any) -> str:
    if isinstance(data, str):
        return data
    payload: dict[str, Any] = {"timestamp": ts(), **extra}
    if isinstance(data, dict):
        payload.update(data)
    elif isinstance(data, list):
        payload["items"] = data
        payload["count"] = len(data)
    else:
        payload["data"] = data
    return json.dumps(payload, indent=2, default=str)


def track_duration(func: Callable) -> Callable:
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.monotonic()
        try:
            result = await func(*args, **kwargs)
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.debug(
                "tool_completed %s %.0fms",
                func.__name__, elapsed_ms,
            )
            return result
        except Exception as exc:
            elapsed_ms = (time.monotonic() - start) * 1000
            logger.error(
                "tool_failed %s %.0fms error=%s",
                func.__name__, elapsed_ms, exc,
            )
            return tool_error(
                func.__name__,
                str(exc),
                suggestion="Check if the backend API is running and accessible.",
            )
    return wrapper


def validate_choice(value: str, valid: set[str], field_name: str = "value") -> str | None:
    cleaned = value.strip().lower()
    if cleaned not in valid:
        sorted_valid = ", ".join(sorted(valid))
        return f"Invalid {field_name} '{value}'. Choose from: {sorted_valid}"
    return None


def clamp(value: int, min_val: int, max_val: int) -> int:
    return max(min_val, min(value, max_val))


def format_table(rows: list[dict[str, Any]], columns: list[str] | None = None) -> str:
    if not rows:
        return "No data."
    cols = columns or list(rows[0].keys())
    widths = {c: len(c) for c in cols}
    for row in rows:
        for c in cols:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    separator = "-+-".join("-" * widths[c] for c in cols)
    lines = [header, separator]
    for row in rows:
        line = " | ".join(str(row.get(c, "")).ljust(widths[c]) for c in cols)
        lines.append(line)
    return "\n".join(lines)


def format_status_emoji(status: str) -> str:
    status_lower = status.lower() if isinstance(status, str) else ""
    mapping = {
        "ok": "OK",
        "healthy": "OK",
        "running": "RUNNING",
        "success": "SUCCESS",
        "up": "UP",
        "error": "ERROR",
        "failed": "FAILED",
        "down": "DOWN",
        "stopped": "STOPPED",
        "paused": "PAUSED",
        "warning": "WARN",
        "critical": "CRITICAL",
        "dead": "DEAD",
        "open": "OPEN",
        "closed": "CLOSED",
    }
    return mapping.get(status_lower, status)


def summary_line(label: str, value: Any, status: str = "") -> str:
    status_str = f" [{format_status_emoji(status)}]" if status else ""
    return f"  {label}: {value}{status_str}"
