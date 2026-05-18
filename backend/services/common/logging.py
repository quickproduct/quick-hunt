"""Shared structured logging setup for API and Celery workers.

All log events automatically include: service, environment, hostname.
Workers call configure_logging() via Celery signals after fork.
API calls it at module load in main.py.

Log files written (when log_to_file=True):
    app.log      — all levels, JSON  (also shipped to Loki via Promtail)
    errors.log   — ERROR+,    JSON  (also shipped to Loki via Promtail)
    warning.log  — WARNING only, human-readable  (end-of-day review)
    error.log    — ERROR   only, human-readable  (end-of-day review)
    critical.log — CRITICAL+,   human-readable  (end-of-day review, + sys.excepthook)

Usage:
    from services.common.logging import configure_logging, log_exception, log_critical_exception

    configure_logging(service_name="scraper", ...)

    try:
        ...
    except Exception as exc:
        log_exception(logger, "task_failed", exc, job_id=job_id)                # → error.log
        log_critical_exception(logger, "fatal_task_error", exc, job_id=job_id)  # → critical.log
"""
import logging
import logging.handlers
import os
import re
import socket
import sys
import traceback
from pathlib import Path
from typing import Any, MutableMapping

import structlog

# ── ANSI strip (safety net for Celery-redirected colored strings) ─────────────

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


# ── Visual separators for human-readable log files ───────────────────────────

_SECTION = "━" * 80
_DIVIDER  = "─" * 40


# ── Exact-level filter ────────────────────────────────────────────────────────

class _ExactLevelFilter(logging.Filter):
    """Allow only log records at *exactly* this level (not higher)."""

    def __init__(self, level: int) -> None:
        super().__init__()
        self._level = level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno == self._level


class _ExcludeNoisyLoggersFilter(logging.Filter):
    """Block loggers that produce high-volume noise in human-readable files.

    celery.redirected: Celery re-emits its own colorized INFO output at
    WARNING level through this logger — not real application warnings.
    """
    _BLOCKED = frozenset({"celery.redirected"})

    def filter(self, record: logging.LogRecord) -> bool:
        return record.name not in self._BLOCKED


# ── Human-readable renderer ───────────────────────────────────────────────────

def _human_readable_renderer(
    _logger: Any,
    _method: str,
    event_dict: MutableMapping[str, Any],
) -> str:
    """Render a structlog event_dict as readable plain text.

    Used by warning.log / error.log / critical.log so engineers can open
    these files in any text editor for end-of-day review without needing
    a JSON viewer.

    Format example:
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        [2026-04-10 19:52:15.123 UTC]  ERROR   services.api.routers.jobs
        Service: api  |  Host: backend-abc  |  Env: development
        ────────────────────────────────────────
          Event      : job_fetch_failed
          request_id : 550e8400-e29b-41d4-a716-446655440000
          path       : /jobs
          status_code: 500

          Exception:
            Type   : DatabaseError
            Message: connection refused

          Traceback:
            Traceback (most recent call last):
              ...
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    """
    ts       = _strip_ansi(str(event_dict.pop("timestamp", "—")))
    level    = _strip_ansi(str(event_dict.pop("level", ""))).upper()
    event    = _strip_ansi(str(event_dict.pop("event", "—")))
    service  = event_dict.pop("service", "?")
    log_name = event_dict.pop("logger", "?")
    hostname = event_dict.pop("hostname", "?")
    env      = event_dict.pop("environment", "?")

    # Exception fields emitted by log_exception() / log_critical_exception()
    exc_type = event_dict.pop("exc_type", None)
    exc_msg  = event_dict.pop("exc_message", None)
    tb_str   = event_dict.pop("traceback", None)

    # Exception dict produced by structlog's ExceptionRenderer (exc_info=True path)
    exception = event_dict.pop("exception", None)

    # Stack info (rarely used, skip silently)
    event_dict.pop("stack_info", None)

    lines: list[str] = [
        _SECTION,
        f"[{ts}]  {level:<8s}  {log_name}",
        f"Service: {service}  |  Host: {hostname}  |  Env: {env}",
        _DIVIDER,
        f"  Event      : {event}",
    ]

    # Remaining context fields (request_id, task_id, job_id, etc.)
    for key, val in event_dict.items():
        lines.append(f"  {key:<10s} : {_strip_ansi(str(val))}")

    # Exception block from log_exception() — exc_type / exc_message / traceback
    if exc_type or exc_msg:
        lines.append("")
        lines.append("  Exception:")
        if exc_type:
            lines.append(f"    Type    : {exc_type}")
        if exc_msg:
            lines.append(f"    Message : {exc_msg}")

    if tb_str:
        lines.append("")
        lines.append("  Traceback:")
        for tb_line in str(tb_str).rstrip().splitlines():
            lines.append(f"    {tb_line}")

    # Exception block from structlog's ExceptionRenderer (exc_info=True)
    if exception:
        lines.append("")
        lines.append("  Exception (exc_info):")
        for exc_line in str(exception).splitlines():
            lines.append(f"    {exc_line}")

    lines.append("")   # blank line after each entry
    return "\n".join(lines)


# ── Global exception hook ─────────────────────────────────────────────────────

def _install_exception_hook() -> None:
    """Redirect all unhandled Python exceptions to CRITICAL in the root logger.

    This means any exception that propagates to the top of the call stack
    (and would normally just print to stderr) is instead captured as a
    CRITICAL log entry and written to critical.log.

    KeyboardInterrupt is intentionally left to the default handler so
    Ctrl-C still works normally.
    """
    def _hook(exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("uncaught_exception").critical(
            "Unhandled exception — process may be in an inconsistent state",
            exc_info=(exc_type, exc_value, exc_tb),
        )

    sys.excepthook = _hook


# ── Standard context processor ────────────────────────────────────────────────

def add_standard_context(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """Structlog processor: inject service, environment, hostname into every event.

    Reads from environment variables so docker-compose SERVICE_NAME flows through
    without any per-service code changes.
    """
    event_dict.setdefault("service", os.environ.get("SERVICE_NAME", "unknown"))
    event_dict.setdefault("environment", os.environ.get("ENVIRONMENT", "development"))
    event_dict.setdefault("hostname", socket.gethostname())
    return event_dict


# ── Main configuration ────────────────────────────────────────────────────────

def configure_logging(
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_to_file: bool = True,
    log_rotation_mb: int = 50,
    environment: str = "development",
    service_name: str = "api",
) -> None:
    """Configure structlog + stdlib logging. Safe to call multiple times.

    Sets SERVICE_NAME and ENVIRONMENT env vars so add_standard_context picks
    them up on every log event without re-passing them at each call site.

    Files created (when log_to_file=True):
        <log_dir>/app.log      — all levels, JSON     — Loki/Promtail source
        <log_dir>/errors.log   — ERROR+, JSON         — Loki/Promtail source
        <log_dir>/warning.log  — WARNING only, text   — end-of-day review
        <log_dir>/error.log    — ERROR only,   text   — end-of-day review
        <log_dir>/critical.log — CRITICAL+,    text   — end-of-day review
    """
    os.environ["SERVICE_NAME"] = service_name
    os.environ.setdefault("ENVIRONMENT", environment)

    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list = [
        add_standard_context,                           # service / env / hostname on every line
        structlog.contextvars.merge_contextvars,        # picks up task_id / request_id bindings
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.ExceptionRenderer(),       # renders exc_info= to exception dict
    ]

    if environment == "development":
        console_renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        console_renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    handlers: list[logging.Handler] = []

    # ── Console handler ───────────────────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=console_renderer,
            foreign_pre_chain=shared_processors,
        )
    )
    handlers.append(console_handler)

    if log_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        max_bytes = log_rotation_mb * 1024 * 1024

        json_formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
        text_formatter = structlog.stdlib.ProcessorFormatter(
            processor=_human_readable_renderer,
            foreign_pre_chain=shared_processors,
        )

        # ── app.log — all levels, JSON (Loki source, unchanged) ──────────────
        app_handler = logging.handlers.RotatingFileHandler(
            log_path / "app.log",
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        app_handler.setLevel(level)
        app_handler.setFormatter(json_formatter)
        handlers.append(app_handler)

        # ── errors.log — ERROR+, JSON (Loki source, unchanged) ───────────────
        loki_error_handler = logging.handlers.RotatingFileHandler(
            log_path / "errors.log",
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        loki_error_handler.setLevel(logging.ERROR)
        loki_error_handler.setFormatter(json_formatter)
        handlers.append(loki_error_handler)

        noisy_filter = _ExcludeNoisyLoggersFilter()

        # ── warning.log — WARNING only, human-readable ────────────────────────
        warning_handler = logging.handlers.RotatingFileHandler(
            log_path / "warning.log",
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        warning_handler.setLevel(logging.WARNING)
        warning_handler.addFilter(_ExactLevelFilter(logging.WARNING))
        warning_handler.addFilter(noisy_filter)
        warning_handler.setFormatter(text_formatter)
        handlers.append(warning_handler)

        # ── error.log — ERROR only, human-readable ────────────────────────────
        error_handler = logging.handlers.RotatingFileHandler(
            log_path / "error.log",
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.addFilter(_ExactLevelFilter(logging.ERROR))
        error_handler.addFilter(noisy_filter)
        error_handler.setFormatter(text_formatter)
        handlers.append(error_handler)

        # ── critical.log — CRITICAL+, human-readable (+ unhandled exceptions) ─
        critical_handler = logging.handlers.RotatingFileHandler(
            log_path / "critical.log",
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        critical_handler.setLevel(logging.CRITICAL)
        critical_handler.addFilter(noisy_filter)
        critical_handler.setFormatter(text_formatter)
        handlers.append(critical_handler)

        # Install sys.excepthook so unhandled exceptions → critical.log
        _install_exception_hook()

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()
    for h in handlers:
        root_logger.addHandler(h)

    for noisy in ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Langfuse emits a WARNING on every task when OTEL/tracing is disabled
    # ("OTEL_SDK_DISABLED is set. Langfuse tracing will be disabled...").
    # Since we intentionally run with LANGFUSE_ENABLED=false, this is pure noise.
    # Raise the threshold to ERROR so only genuine Langfuse failures surface.
    logging.getLogger("langfuse").setLevel(logging.ERROR)



# ── Exception logging helpers ─────────────────────────────────────────────────

def log_exception(
    logger: Any,
    event: str,
    exc: Exception,
    **kwargs: Any,
) -> None:
    """Log an exception at ERROR level with full traceback as structured fields.

    Use in Celery task except blocks. Writes to error.log (human-readable)
    and errors.log / app.log (JSON, Loki).

    Emits:
        exc_type    — class name, e.g. "ConnectionError"
        exc_message — str(exc)
        traceback   — full formatted traceback string

    Example:
        except Exception as exc:
            log_exception(logger, "task_failed", exc, job_id=job_id)
            raise self.retry(exc=exc)
    """
    logger.error(
        event,
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        traceback=traceback.format_exc(),
        **kwargs,
    )


def log_critical_exception(
    logger: Any,
    event: str,
    exc: Exception,
    **kwargs: Any,
) -> None:
    """Log an exception at CRITICAL level — use for unrecoverable errors.

    Writes to critical.log (human-readable) and app.log / errors.log (JSON, Loki).
    Also triggers any alerting wired to CRITICAL level.

    Use when the system is in an inconsistent state or data loss is possible.

    Example:
        except Exception as exc:
            log_critical_exception(logger, "db_migration_failed", exc)
            raise SystemExit(1)
    """
    logger.critical(
        event,
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        traceback=traceback.format_exc(),
        **kwargs,
    )
