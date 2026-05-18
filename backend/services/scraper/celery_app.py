"""Celery application with task routing and beat schedule.

Broker strategy — unified RabbitMQ architecture:
  - All queues use RabbitMQ for task dispatching
  - Workers connect to RabbitMQ by default
  - Result backend: always Redis (Upstash) — fast key-value, ideal for results

  Queue organization:
  - Scraping queues: jh_scraping_bulk, jh_scraping_realtime, jh_scraping_enrichment
  - Cover letter queues: jh_cover_letter_bulk, jh_cover_letter_ranking, jh_cover_letter_generation, jh_cover_letter_workflow
  - Email queues: jh_email_send, jh_email_retry
  - Maintenance queue: jh_jobs_maintenance
"""

import os
import ssl

from services.api.core.config import get_settings

settings = get_settings()

# ── Broker URL resolution ─────────────────────────────────────────────────────
# IMPORTANT: Celery 5 reads CELERY_BROKER_URL from the OS environment and it
# overrides conf.update() and even direct conf assignment.  We must set the
# env var to our computed value BEFORE importing/instantiating Celery.

_rabbit_url = settings.rabbitmq_url          # amqps:// CloudAMQP (empty = not set)
_redis_broker = settings.celery_broker_url     # rediss:// Upstash / redis:// local

# Broker selection — require RabbitMQ to be explicitly configured in prod.
# Falling back silently to Redis was masking misconfiguration; fail loud instead
# (unless redis is the only option, e.g. local dev with RABBITMQ_URL not set).
if not _rabbit_url and not _redis_broker:
    raise RuntimeError(
        "No broker configured. Set RABBITMQ_URL (preferred) or CELERY_BROKER_URL in .env."
    )

if _rabbit_url:
    _broker_url = _rabbit_url
    _broker_is_amqp = True
else:
    _broker_url = _redis_broker
    _broker_is_amqp = False

# Override CELERY_BROKER_URL env var so Celery 5's env-var reader picks up our
# computed value instead of the raw CELERY_BROKER_URL (which always points to Redis).
os.environ["CELERY_BROKER_URL"] = _broker_url

from celery import Celery  # noqa: E402 — must come after env override
from celery.schedules import crontab  # noqa: E402
from celery.signals import beat_init, worker_init, worker_process_init  # noqa: E402

celery_app = Celery("job_hunter")

# ── Structured logging initialization for workers ────────────────────────────
# configure_logging() must run in each worker process after the fork.
# • worker_process_init — fires in each prefork child where tasks actually run.
# • worker_init          — fires in the main (supervisor) process: covers beat,
#                          flower, and the master worker process itself.
# SERVICE_NAME is set by docker-compose per-service so Kibana can filter by it.
def _setup_worker_logging() -> None:
    from services.common.logging import configure_logging
    configure_logging(
        log_level=settings.log_level,
        log_dir=settings.log_dir,
        log_to_file=settings.log_to_file,
        log_rotation_mb=settings.log_rotation_mb,
        environment=settings.environment,
        service_name=os.environ.get("SERVICE_NAME", "scraper"),
    )

@worker_process_init.connect
def _init_worker_process_logging(**kwargs):
    _setup_worker_logging()

@worker_init.connect
def _init_worker_main_logging(**kwargs):
    _setup_worker_logging()

@beat_init.connect
def _init_beat_logging(**kwargs):
    # beat_init fires in the celery beat scheduler process (not a worker process).
    _setup_worker_logging()

# ── SSL options ───────────────────────────────────────────────────────────────
# Local Docker services use plain amqp:// and redis:// (no TLS needed).
# Cloud services (Upstash rediss://, CloudAMQP amqps://) need explicit SSL opts.
_result_uses_ssl = settings.celery_result_backend.startswith("rediss://")
_redis_ssl_opts = {"ssl_cert_reqs": ssl.CERT_NONE} if _result_uses_ssl else None

# Broker SSL: only needed when the broker URL is rediss:// (pure Redis-TLS broker).
# • amqps:// handles TLS automatically via the URL scheme.
# • amqp:// / redis:// (local Docker) — no SSL options needed.
_broker_ssl_opts = (
    {"ssl_cert_reqs": ssl.CERT_NONE}
    if (not _broker_is_amqp and _broker_url.startswith("rediss://"))
    else None
)

# ── App config ────────────────────────────────────────────────────────────────
celery_app.conf.update(
    broker_url=_broker_url,
    result_backend=settings.celery_result_backend,
    broker_use_ssl=_broker_ssl_opts,
    redis_backend_use_ssl=_redis_ssl_opts,
    include=[
        "services.scraper.tasks",
        "services.ai.tasks",
        "services.sender.tasks",
    ],
    task_serializer="json",
    accept_content=["json", "application/x-gzip"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=settings.worker_prefetch_multiplier,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=None,
    # Do NOT cancel running tasks on AMQP connection loss.
    # When True, Celery calls mark_as_revoked() → Redis write.
    # If Redis is also idle-dropped at the same moment, this causes
    # "CRITICAL: Unrecoverable error: ConnectionError" and a worker crash.
    # With task_acks_late=True the task will re-ack after broker reconnects.
    worker_cancel_long_running_tasks_on_connection_loss=False,
    # AMQP heartbeat — only meaningful for a pure RabbitMQ broker connection.
    # 30 s → Celery sends AMQP heartbeats every 15 s (half the value).
    # CloudAMQP drops connections silent after 60 s of no AMQP activity;
    # 15-s ping cadence gives 4× headroom even if one beat is delayed.
    broker_heartbeat=30 if _broker_is_amqp else None,
    # Check heartbeat twice per interval (default 2, explicit for clarity).
    broker_heartbeat_checkrate=2,
    # Producer connection pool — kept small to stay under CloudAMQP free tier's
    # 20-connection limit.  2 workers×3 + beat(1) + flower(1) + api-pool(3) = 11.
    broker_pool_limit=settings.broker_pool_limit,
    broker_transport_options={
        "socket_connect_timeout": 10,
        "retry_on_timeout": True,
        "health_check_interval": 10,
        # Retry the TCP connection before giving up on a task publish.
        # Delays: 0 s, 1 s, 2 s, … capped at 5 s → ~35 s total cover window.
        # This absorbs 20-30 s RabbitMQ restarts without logging SchedulingError.
        "max_retries": 10,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 5,
    },
    result_backend_transport_options={
        "socket_keepalive": True,
        "socket_timeout": 30,
        "socket_connect_timeout": 30,
        "retry_on_timeout": True,
        "health_check_interval": 10,
        "retry_policy": {"timeout": 10.0},
    },
    task_routes={
        # ── Scraping (RabbitMQ) ────────────────────────────────────────────────
        "services.scraper.tasks.scheduled_scrape":           {"queue": "jh_scraping_bulk"},
        "services.scraper.tasks.scrape_portal_task":         {"queue": "jh_scraping_realtime"},
        "services.scraper.tasks.backfill_hr_emails_task":        {"queue": "jh_scraping_enrichment"},
        "services.scraper.tasks.fix_placeholder_emails_task":     {"queue": "jh_scraping_enrichment"},
        # ── Maintenance (Redis) ─────────────────────────────────────────────────
        "services.scraper.tasks.deduplicate_jobs_task":           {"queue": "jh_jobs_maintenance"},
        "services.scraper.tasks.cleanup_old_jobs_task":           {"queue": "jh_jobs_maintenance"},
        "services.scraper.tasks.pipeline_health_check_task":      {"queue": "jh_jobs_maintenance"},
        "services.scraper.tasks.stale_lock_reaper_task":          {"queue": "jh_jobs_maintenance"},
        "services.scraper.tasks.purge_old_cron_runs_task":        {"queue": "jh_jobs_maintenance"},
        # ── Cover Letter / AI (Redis) ───────────────────────────────────────────
        "services.ai.tasks.fill_missing_covers_task":             {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.refresh_cover_letters_task":           {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.refresh_non_php_covers_task":          {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.check_cover_letter_status_task":       {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.score_job_task":                       {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.rank_jobs_task":                       {"queue": "jh_cover_letter_ranking"},
        "services.ai.tasks.generate_cover_letter_task":           {"queue": "jh_cover_letter_generation"},
        # Embeddings get their own queue — they're fast and shouldn't block
        # Groq-rate-limited cover generation workers.
        "services.ai.tasks.generate_embedding_task":              {"queue": "jh_embeddings"},
        # Workflow task kept for routing but no longer dispatched from scraper.
        "services.ai.tasks.run_application_workflow_task":        {"queue": "jh_cover_letter_workflow"},
        # Batch queue — single-concurrency worker drains at GROQ_RPM/min
        "services.ai.tasks.enqueue_cover_letter_task":            {"queue": "jh_cover_letter_batch"},
        "services.ai.tasks.flush_cover_batch_task":               {"queue": "jh_cover_letter_batch"},
        # ── Email (Redis) ─────────────────────────────────────────────────────
        "services.sender.tasks.send_application_email_task":      {"queue": "jh_email_send"},
        "services.sender.tasks.retry_failed_sends_task":          {"queue": "jh_email_retry"},
        "services.sender.tasks.dispatch_ready_to_send_task":      {"queue": "jh_email_send"},
        "services.sender.tasks.auto_approve_pending_jobs_task":   {"queue": "jh_email_send"},
    },
    # Task time limits — configurable via infra/worker.config.yml.
    # Soft limit: task gets SoftTimeLimitExceeded (can clean up).
    # Hard limit: worker forcibly kills the task.
    task_soft_time_limit=settings.task_soft_time_limit,
    task_time_limit=settings.task_time_limit,
    # Compress large task payloads (e.g. long job descriptions passed as args).
    task_compression="gzip",
    # Never try to store task results/failures in Redis — avoids ConnectionError
    # whenOT write task state (errors/retries) to the result backend when
    # task_ignore_result=True.  Without this, a connection drop on AMQP triggers
    # mark_as_retry() → Upstash Redis write → Redis idle-connection error →
    # CRITICAL: Unrecoverable error → worker crash.  Setting this False breaks
    # that cascade entirely: no Redis write happens during connection loss.
    task_store_errors_even_if_ignored=False,
    # Beat schedule — all queues use RabbitMQ.
    # 5-min tasks are staggered via crontab offsets to avoid thundering herd on DB/queues.
    beat_schedule={
        "scrape-every-2-hours": {
            "task": "services.scraper.tasks.scheduled_scrape",
            "schedule": settings.beat_scrape_interval,
        },
        "refresh-cover-letters-every-4-hours": {
            "task": "services.ai.tasks.refresh_cover_letters_task",
            "schedule": settings.beat_refresh_covers_interval,
        },
        # ── Staggered 5-min group (offset by 1 min each) ─────────────────────
        "deduplicate-jobs-every-15min": {
            "task": "services.scraper.tasks.deduplicate_jobs_task",
            "schedule": crontab(minute="0,15,30,45"),
        },
        "backfill-hr-emails-every-5min": {
            "task": "services.scraper.tasks.backfill_hr_emails_task",
            "schedule": crontab(minute="1,6,11,16,21,26,31,36,41,46,51,56"),
        },
        "fill-missing-covers-every-5min": {
            "task": "services.ai.tasks.fill_missing_covers_task",
            "schedule": crontab(minute="2,7,12,17,22,27,32,37,42,47,52,57"),
        },
        "refresh-non-php-covers-every-30min": {
            "task": "services.ai.tasks.refresh_non_php_covers_task",
            "schedule": crontab(minute="3,33"),
        },
        # ── 10-min tasks ─────────────────────────────────────────────────────
        "stale-lock-reaper-every-10min": {
            "task": "services.scraper.tasks.stale_lock_reaper_task",
            "schedule": crontab(minute="3,13,23,33,43,53"),
        },
        # ── 15-min tasks ─────────────────────────────────────────────────────
        "pipeline-health-check-every-15min": {
            "task": "services.scraper.tasks.pipeline_health_check_task",
            "schedule": crontab(minute="4,19,34,49"),
        },
        # ── 30-min tasks ─────────────────────────────────────────────────────
        "fix-placeholder-emails-every-30min": {
            "task": "services.scraper.tasks.fix_placeholder_emails_task",
            "schedule": settings.beat_fix_placeholder_interval,
        },
        # ── Hourly ───────────────────────────────────────────────────────────
        "check-cover-letter-status-hourly": {
            "task": "services.ai.tasks.check_cover_letter_status_task",
            "schedule": settings.beat_cover_status_interval,
        },
        # ── Daily / weekly ───────────────────────────────────────────────────
        "cleanup-old-jobs-weekly": {
            "task": "services.scraper.tasks.cleanup_old_jobs_task",
            "schedule": settings.beat_cleanup_interval,
        },
        "purge-old-cron-runs-nightly": {
            "task": "services.scraper.tasks.purge_old_cron_runs_task",
            "schedule": 86400,  # once per day
        },
        # ── DISABLED — auto-send off globally (AUTO_SEND_ENABLED=False) ──────
        # "retry-failed-sends-every-30min": {
        #     "task": "services.sender.tasks.retry_failed_sends_task",
        #     "schedule": settings.beat_retry_sends_interval,
        # },
        # "dispatch-ready-to-send-every-5min": {
        #     "task": "services.sender.tasks.dispatch_ready_to_send_task",
        #     "schedule": settings.beat_dispatch_ready_interval,
        # },
        # "auto-approve-pending-every-10min": {
        #     "task": "services.sender.tasks.auto_approve_pending_jobs_task",
        #     "schedule": settings.beat_auto_approve_interval,
        # },
    },
)


# Portal adapter registry — only portals confirmed to return jobs are included.
#
# DISABLED portals (adapter files kept for future re-enablement):
#   Indian portals (JS-rendered / bot-blocked):
#     linkedin   — httpx returns JS-rendered shell; 0 jobs without Playwright or official API
#     timesjobs  — Next.js SPA, no API
#     foundit    — React SPA, no public API
#     iimjobs    — JS-rendered, empty LD+JSON
#     apna       — React SPA, Playwright blocked
#     cutshort   — GraphQL, requires auth
#     instahyre  — Next.js SPA, REST API 404
#     wellfound  — Cloudflare + GraphQL, requires auth
#     freshersworld — all URL patterns return 404
#     glassdoor  — Playwright blocked, 0 jobs
#     angellist  — Playwright blocked (Wellfound/Cloudflare), 0 jobs
#   Remote portals (bot-blocked / timeout):
#     remotive   — Cloudflare 526
#     remoteco   — WP REST API timeout
#     himalayas  — 403 on all endpoints
#     arcdev     — React SPA, no public API
#     justremote — styled-components SPA
#     nodesk     — JS-rendered, Playwright blocked
def _get_disabled_portals() -> set[str]:
    """Check Redis for admin-disabled portals. Returns set of disabled portal names."""
    try:
        import redis as sync_redis
        settings = get_settings()
        r = sync_redis.from_url(
            settings.redis_url, decode_responses=True,
            socket_timeout=2, socket_connect_timeout=2,
        )
        keys = [f"admin:portal:{portal}:enabled" for portal in VALID_PORTALS]
        values = r.mget(keys)
        disabled = set()
        for portal, val in zip(VALID_PORTALS, values):
            if val == "false":
                disabled.add(portal)
        r.close()
        return disabled
    except Exception:
        return set()


def get_adapter_registry():
    from services.scraper.adapters.indeed import IndeedAdapter
    from services.scraper.adapters.naukri import NaukriAdapter
    from services.scraper.adapters.shine import ShineAdapter
    from services.scraper.adapters.internshala import InternshalaAdapter
    from services.scraper.adapters.remoteok import RemoteOKAdapter
    from services.scraper.adapters.weworkremotely import WeWorkRemotelyAdapter
    from services.scraper.adapters.workingnomads import WorkingNomadsAdapter
    from services.scraper.adapters.jobspresso import JobspressoAdapter

    all_adapters = {
        "naukri": NaukriAdapter,
        "indeed": IndeedAdapter,
        "shine": ShineAdapter,
        "internshala": InternshalaAdapter,
        "remoteok": RemoteOKAdapter,
        "weworkremotely": WeWorkRemotelyAdapter,
        "workingnomads": WorkingNomadsAdapter,
        "jobspresso": JobspressoAdapter,
    }

    disabled = _get_disabled_portals()
    if disabled:
        return {k: v for k, v in all_adapters.items() if k not in disabled}
    return all_adapters


VALID_PORTALS = {
    "naukri", "indeed", "shine", "internshala",
    "remoteok", "weworkremotely", "workingnomads", "jobspresso",
}
