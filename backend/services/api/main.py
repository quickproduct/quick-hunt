"""FastAPI application factory."""
import asyncio
import time
import traceback
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from services.api.core.config import get_settings
from services.common.logging import configure_logging

# Configure logging immediately at module load so all imports that follow
# use the configured structlog setup.
_settings = get_settings()
configure_logging(
    log_level=_settings.log_level,
    log_dir=_settings.log_dir,
    log_to_file=_settings.log_to_file,
    log_rotation_mb=_settings.log_rotation_mb,
    environment=_settings.environment,
    service_name="api",
)

logger = structlog.get_logger(__name__)


async def _db_keepalive() -> None:
    """Ping DB every 4 min to keep Neon compute alive.

    Only active when POSTGRES_LOCAL=false (Neon serverless).
    Neon suspends compute after ~5 min of inactivity; a periodic SELECT 1
    keeps compute running so every request hits a warm DB.
    """
    from services.api.core.database import get_worker_session_factory
    sf = get_worker_session_factory()
    while True:
        await asyncio.sleep(240)  # 4 min — well under Neon's 5-min idle timeout
        try:
            async with sf() as session:
                await session.execute(text("SELECT 1"))
            logger.info("db_keepalive_ok")
        except Exception as exc:
            logger.warning("db_keepalive_failed", error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown."""
    settings = get_settings()
    logger.info(
        "app_starting",
        environment=settings.environment,
        log_dir=settings.log_dir,
        llm_provider=settings.llm_provider,
        vector_db=settings.vector_db_provider,
        email_provider=settings.email_provider,
        postgres_local=settings.postgres_local,
    )

    # Warm up the DB connection pool in the background so the server starts
    # accepting requests immediately without waiting for pool authentication.
    async def _warmup():
        from services.api.core.database import get_session_factory
        sf = get_session_factory()

        async def _warm_one():
            try:
                async with sf() as s:
                    await s.execute(text("SELECT 1"))
            except Exception as exc:
                logger.warning("db_warmup_one_failed", error=str(exc))

        try:
            await asyncio.gather(*[_warm_one() for _ in range(10)])  # pool_size=10
            logger.info("db_pool_warmed_up")
        except Exception as exc:
            logger.warning("db_warmup_failed", error=str(exc))

        # Keep Neon compute alive — skip for local Docker postgres.
        if not settings.postgres_local:
            await _db_keepalive()  # runs forever

    keepalive = asyncio.create_task(_warmup())
    yield
    keepalive.cancel()
    try:
        await keepalive
    except asyncio.CancelledError:
        pass
    logger.info("app_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="AI Job Hunter Bot",
        version="1.0.0",
        description="Automated job application bot — scrape, rank, apply.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.environment == "development" else ["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Prometheus metrics — exposes /metrics for Prometheus scraping.
    # Instruments all HTTP routes automatically (request count, latency histograms).
    from prometheus_fastapi_instrumentator import Instrumentator
    from prometheus_fastapi_instrumentator import metrics as pfi_metrics
    (
        Instrumentator(
            should_group_status_codes=False,  # track 200/201/4xx/5xx individually
            excluded_handlers=["/metrics", "/health"],
        )
        .instrument(app)
        .add(
            pfi_metrics.requests(),  # http_requests_total{handler,method,status}
            pfi_metrics.latency(),   # http_request_duration_seconds{handler,method,status}
        )
        .expose(app, endpoint="/metrics", include_in_schema=False)
    )

    # HTTP request logging middleware — logs every request; routes unhandled
    # exceptions and 5xx responses to CRITICAL so they land in critical.log.
    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        start = time.perf_counter()

        try:
            response: Response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)

            # ── DB connectivity errors → 503 Service Unavailable ─────────
            # During DB maintenance / Neon suspend-resume the asyncpg pool
            # raises these.  Returning 503 (instead of 500) tells clients and
            # load-balancers the outage is temporary and they should retry.
            _DB_ERROR_NAMES = {
                "InterfaceError",
                "ConnectionDoesNotExistError",
                "ConnectionRefusedError",
                "CannotConnectNowError",
                "PostgresConnectionError",
            }
            exc_name = type(exc).__name__
            exc_module = type(exc).__module__ or ""
            is_db_error = (
                exc_name in _DB_ERROR_NAMES
                or "sqlalchemy" in exc_module.lower()
                or "asyncpg" in exc_module.lower()
                or "psycopg" in exc_module.lower()
            )

            if is_db_error:
                logger.warning(
                    "db_error_returning_503",
                    exc_type=exc_name,
                    exc_message=str(exc)[:300],
                    method=request.method,
                    path=request.url.path,
                    duration_ms=duration_ms,
                    request_id=request_id,
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Database temporarily unavailable. Please retry.",
                        "request_id": request_id,
                    },
                    headers={"Retry-After": "5", "X-Request-ID": request_id},
                )

            # Unhandled exception propagated out of a route handler — this
            # should never happen in normal operation. Log it as CRITICAL so it
            # goes into critical.log, then re-raise so FastAPI returns a 500.
            logger.critical(
                "unhandled_http_exception",
                exc_type=exc_name,
                exc_message=str(exc),
                traceback=traceback.format_exc(),
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
                request_id=request_id,
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Log 5xx responses as CRITICAL so they also appear in critical.log.
        # These are server-side failures (not 4xx client errors).
        if response.status_code >= 500:
            logger.critical(
                "http_server_error",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    # Routers
    from services.api.routers import (
        admin,
        auth,
        billing,
        blacklist,
        candidates,
        consulting_companies,
        hr_emails,
        jobs,
        mnc_companies,
        search,
        send,
        stats,
        tenants,
        users,
        webhooks,
    )

    # Auth / SaaS routers (no prefix conflicts)
    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(tenants.router)
    app.include_router(billing.router)

    # Core business routers
    app.include_router(candidates.router)
    app.include_router(blacklist.router)
    app.include_router(mnc_companies.router)
    app.include_router(consulting_companies.router)
    # send.router must come before jobs.router so that GET /jobs/send_logs
    # is registered before GET /jobs/{job_id} — FastAPI matches in order.
    app.include_router(send.router)
    app.include_router(jobs.router)
    app.include_router(search.router)
    app.include_router(stats.router)
    app.include_router(hr_emails.router)
    app.include_router(webhooks.router)

    # Admin / ops management router
    app.include_router(admin.router)

    @app.get("/health", tags=["health"])
    async def health():
        return {
            "status": "ok",
            "version": "1.0.0",
            "environment": settings.environment,
        }

    @app.get("/", tags=["root"])
    async def root():
        return {
            "name": "AI Job Hunter Bot API",
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
