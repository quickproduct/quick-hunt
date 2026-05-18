"""Shared async utilities for Celery task files."""
import asyncio
import logging
import threading


_loop_local = threading.local()
_loop_lock = threading.Lock()

log = logging.getLogger(__name__)


def _dispose_engine_pools() -> None:
    """Dispose all async engine pools so they rebind to the new event loop.

    When the persistent event loop is recreated (e.g. after a DB restart or
    recovery), existing asyncpg connections are bound to the *old* (now dead)
    loop.  Disposing the pool forces new connections on the new loop and
    prevents ``RuntimeError: Future attached to a different loop``.
    """
    try:
        from services.api.core.database import _get_worker_engine
        engine = _get_worker_engine()
        if engine and hasattr(engine, 'pool') and engine.pool:
            engine.pool.dispose()
    except Exception:
        pass

    try:
        from services.api.core.database import _get_engine
        engine = _get_engine()
        if engine and hasattr(engine, 'pool') and engine.pool:
            engine.pool.dispose()
    except Exception:
        pass


def _reset_engine_singletons() -> None:
    """Reset database engine singletons so they are recreated on the new loop.

    Called when the old event loop is already closed. We CANNOT close asyncpg
    connections here — any attempt raises RuntimeError: Future attached to a
    different loop. Instead, null out the singletons; the next task creates
    fresh engines bound to the current loop. Abandoned TCP sockets are reclaimed
    by the OS or timed out by the DB server.

    Worker singletons are now thread-local (_worker_thread_local), so we reset
    the current thread's slot.  API singletons (_engine, _session_factory) are
    process-globals and are reset unconditionally.
    """
    try:
        import services.api.core.database as _db
        # Reset thread-local worker pool (primary fix for @cron_safe cross-loop)
        tl = getattr(_db, "_worker_thread_local", None)
        if tl is not None:
            tl.engine = None
            tl.session_factory = None
        # Legacy process-global stubs (kept for any external references)
        _db._worker_engine = None
        _db._worker_session_factory = None
        # API singletons
        _db._engine = None
        _db._session_factory = None
    except Exception:
        pass

    # Reset the shared aioredis client — it holds connections bound to the old
    # loop. Nulling it forces get_redis() to create a fresh client on the new loop,
    # preventing "Event loop is closed" errors in cron_validators._record_success.
    try:
        import services.api.core.cache as _cache
        _cache._redis_client = None
    except Exception:
        pass


async def _graceful_dispose() -> None:
    """Dispose engine pools within a proper async context.

    Called during worker shutdown so that asyncpg connections are closed
    inside an active event loop, preventing MissingGreenlet errors.
    """
    try:
        from services.api.core.database import _get_worker_engine, _get_engine
        for getter in (_get_worker_engine, _get_engine):
            try:
                engine = getter()
                if engine:
                    await engine.dispose()
            except Exception:
                pass
    except Exception:
        pass


def _flush_langfuse() -> None:
    """Flush Langfuse callback handler so traces are not lost on shutdown."""
    try:
        from langfuse.callback import CallbackHandler  # type: ignore[import]
        handler = CallbackHandler.__instance__ if hasattr(CallbackHandler, "__instance__") else None
        if handler and hasattr(handler, "flush"):
            handler.flush()
    except Exception:
        pass

    # Also try flushing via the module-level client if present
    try:
        import langfuse as _lf  # type: ignore[import]
        client = getattr(_lf, "_client", None) or getattr(_lf, "client", None)
        if client and hasattr(client, "flush"):
            client.flush()
    except Exception:
        pass


def _on_worker_shutdown(**kwargs) -> None:
    """Celery signal handler: gracefully dispose async engine pools.

    Without this, SQLAlchemy's AsyncAdaptedQueuePool tries to close
    asyncpg connections during garbage collection when no greenlet/event
    loop is active, raising MissingGreenlet errors.
    """
    _flush_langfuse()

    loop = getattr(_loop_local, 'loop', None)
    if loop and not loop.is_closed():
        try:
            loop.run_until_complete(_graceful_dispose())
        except Exception:
            pass
    else:
        _reset_engine_singletons()

    if loop and not loop.is_closed():
        try:
            loop.close()
        except Exception:
            pass
    _loop_local.loop = None


try:
    from celery.signals import worker_process_shutdown
    worker_process_shutdown.connect(_on_worker_shutdown)
except Exception:
    pass


def _worker_loop() -> asyncio.AbstractEventLoop:
    """Return the persistent event loop for this worker thread.

    Celery prefork workers each run in their own OS process. Within a
    process we reuse one event loop so that SQLAlchemy's async connection
    pool (which binds to the loop it was first created on) stays valid
    across task invocations.  asyncio.run() creates *and closes* a new
    loop each call, which invalidates the pool and raises:
        RuntimeError: Future <...> attached to a different loop
    """
    needs_reset = (
        not hasattr(_loop_local, 'loop')
        or _loop_local.loop is None
        or _loop_local.loop.is_closed()
    )
    if needs_reset:
        with _loop_lock:
            needs_reset = (
                not hasattr(_loop_local, 'loop')
                or _loop_local.loop is None
                or _loop_local.loop.is_closed()
            )
            if needs_reset:
                _loop_local.loop = asyncio.new_event_loop()
                asyncio.set_event_loop(_loop_local.loop)
                try:
                    _reset_engine_singletons()
                except Exception:
                    pass
    return _loop_local.loop


def run_async(coro):
    """Run an async coroutine from a synchronous Celery task.

    Uses a persistent per-thread event loop so SQLAlchemy connection
    pools remain valid between task invocations.
    """
    return _worker_loop().run_until_complete(coro)
