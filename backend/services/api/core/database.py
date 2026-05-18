import threading
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from services.api.core.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    """API engine — larger pool for concurrent HTTP request handling."""
    settings = get_settings()
    kwargs: dict = dict(
        pool_size=20,
        max_overflow=20,   # 40 max connections per API process
        pool_timeout=30,   # tolerate checkpoint I/O spikes (was 10)
        echo=False,
        pool_pre_ping=True,  # Always validate connections — detects stale/bad-state
    )
    if not settings.postgres_local:
        # Neon serverless: recycle connections before the 5-min idle suspend,
        # disable JIT (Neon rec).
        kwargs["pool_recycle"] = 240
        kwargs["connect_args"] = {"server_settings": {"jit": "off", "statement_timeout": "60000"}}
    else:
        kwargs["connect_args"] = {"server_settings": {"statement_timeout": "60000"}}
    return create_async_engine(settings.database_url, **kwargs)


def get_worker_engine():
    """Worker engine — optimized pool sized for Celery prefork processes.

    Each Celery worker is a separate OS process.  Tasks are async but share
    one event loop per process.  Some workers (enrichment, cover-generation)
    run with concurrency > 1, so pool_size=3 + max_overflow=7 avoids
    QueuePool exhaustion while keeping the connection budget reasonable.

    Connection budget:
      ~84 worker processes × 10 = 840 max connections worst-case.
      Typical usage is far lower since most workers are idle between tasks.
      With postgres max_connections=400, the pool_pre_ping + pool_timeout
      ensures connections are returned promptly.
    """
    settings = get_settings()
    kwargs: dict = dict(
        pool_size=3,
        max_overflow=7,
        pool_timeout=60,
        pool_pre_ping=True,
        echo=False,
        pool_recycle=-1,
    )
    if not settings.postgres_local:
        kwargs["connect_args"] = {"server_settings": {"jit": "off"}}
    return create_async_engine(settings.database_url, **kwargs)


def get_session_factory(engine=None):
    if engine is None:
        engine = get_engine()
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


# ── API process singletons (process-level, safe — API has one event loop) ────
_engine = None
_session_factory = None

# ── Worker thread-locals (one engine+pool per OS thread) ─────────────────────
# @cron_safe runs each task in a NEW OS thread with a NEW asyncio event loop.
# asyncpg connections are bound to the event loop that created them.  If the
# engine were a process-global, Thread-2's loop would receive connections that
# Thread-1's loop created → "Future attached to a different loop" crash.
# Making the engine thread-local means each thread lazily creates its own pool
# bound to its own loop, eliminating the cross-loop contamination.
_worker_thread_local = threading.local()

# Legacy names kept so async_utils._reset_engine_singletons still compiles.
_worker_engine = None
_worker_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine


def _get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = get_session_factory(_get_engine())
    return _session_factory


def _get_worker_engine():
    if not getattr(_worker_thread_local, "engine", None):
        _worker_thread_local.engine = get_worker_engine()
    return _worker_thread_local.engine


def _get_worker_session_factory():
    if not getattr(_worker_thread_local, "session_factory", None):
        _worker_thread_local.session_factory = get_session_factory(_get_worker_engine())
    return _worker_thread_local.session_factory


def get_worker_session_factory():
    """Return the thread-local session factory for Celery workers.

    Thread-local (not process-global) so that each OS thread spawned by
    @cron_safe gets its own asyncpg connection pool bound to its own event
    loop.  Never call get_session_factory(get_engine()) inside a task — that
    creates a new engine per call, leaking connections.
    """
    return _get_worker_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with _get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
