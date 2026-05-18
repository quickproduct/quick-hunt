"""Langfuse observability — singleton client + callback handler factory (v4 SDK).

Every LLM call in this project is instrumented:
  - LangfuseCallbackHandler  → LangChain / LangGraph calls (ChatGroq via langchain-groq)
  - lf.start_observation()   → direct OpenAI-SDK calls (GroqAdapter.generate_text)

Traces are organised by trace_id=job_id so every event for a job
is grouped together in the Langfuse dashboard.

Configure via infra/.env:
  LANGFUSE_ENABLED=true
  LANGFUSE_PUBLIC_KEY=pk-lf-...
  LANGFUSE_SECRET_KEY=sk-lf-...
  LANGFUSE_BASE_URL=https://cloud.langfuse.com   # or self-hosted URL

Leave LANGFUSE_ENABLED=false (default) to disable without removing keys.
"""
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

import structlog

if TYPE_CHECKING:
    from langfuse import Langfuse
    from langfuse.langchain import CallbackHandler

logger = structlog.get_logger(__name__)

_lock = threading.Lock()
_client: Optional["Langfuse"] = None
_enabled: Optional[bool] = None  # cached after first check


# ── Internal helpers ──────────────────────────────────────────────────────────

def _settings():
    from services.api.core.config import get_settings
    return get_settings()


def is_enabled() -> bool:
    """Return True when Langfuse is configured and enabled."""
    global _enabled
    if _enabled is None:
        s = _settings()
        _enabled = (
            getattr(s, "langfuse_enabled", False)
            and bool(getattr(s, "langfuse_public_key", ""))
            and bool(getattr(s, "langfuse_secret_key", ""))
        )
    return _enabled


# ── Public API ────────────────────────────────────────────────────────────────

def get_langfuse() -> Optional["Langfuse"]:
    """Return singleton Langfuse client (v4), or None when disabled / unconfigured.

    Langfuse v4 reads LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY / LANGFUSE_HOST
    from environment variables automatically, so no explicit key passing is needed.
    """
    global _client
    if not is_enabled():
        return None
    if _client is None:
        with _lock:
            if _client is None:
                try:
                    from langfuse import get_client
                    _client = get_client()
                    s = _settings()
                    logger.info("langfuse_initialized", host=s.langfuse_host)
                except Exception as exc:
                    logger.warning("langfuse_init_failed", error=str(exc))
    return _client


def get_callback_handler(
    trace_name: str,
    *,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> Optional["CallbackHandler"]:
    """Return a LangfuseCallbackHandler for a LangChain / LangGraph invocation.

    Returns None when Langfuse is disabled so callers can safely do:
        callbacks = [h] if (h := get_callback_handler(...)) else []

    In langfuse v4 the handler is auto-configured via env vars.
    Pass session_id=job_id to group all LLM calls for one job under one trace.
    """
    if not is_enabled():
        return None
    try:
        from langfuse.langchain import CallbackHandler
        # trace_context with trace_id groups all LangChain calls for the same
        # job under one trace in the Langfuse dashboard.
        # langfuse v4 requires a 32 lowercase hex char trace ID (OTEL format) —
        # strip hyphens from UUID so "abc-def-..." becomes "abcdef...".
        trace_context: dict = {}
        if session_id:
            trace_context["trace_id"] = session_id.replace("-", "")
        return CallbackHandler(trace_context=trace_context or None)
    except Exception as exc:
        logger.warning("langfuse_handler_create_failed", trace=trace_name, error=str(exc))
        return None


def flush() -> None:
    """Flush all pending Langfuse events to the server.

    Call at the end of every Celery task to ensure events are not lost
    when the worker process is idle or recycled.
    """
    client = get_langfuse()
    if client:
        try:
            client.flush()
        except Exception:
            pass
