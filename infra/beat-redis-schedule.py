"""Beat scheduler configuration for Redis queues.

This module provides a separate Celery app configuration for the Redis beat scheduler,
which dispatches tasks to Redis queues: jh_jobs_maintenance, jh_cover_letter_*, jh_email_*
"""

import os
import ssl

from services.api.core.config import get_settings

settings = get_settings()

# Force Redis broker for this beat scheduler
os.environ["CELERY_BROKER_URL"] = settings.celery_broker_url

from celery import Celery

beat_redis_app = Celery("beat_redis")

beat_redis_app.conf.update(
    broker_url=settings.celery_broker_url,
    result_backend=settings.celery_result_backend,
    broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE} if settings.celery_broker_url.startswith("rediss://") else None,
    redis_backend_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE} if settings.celery_result_backend.startswith("rediss://") else None,
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
    task_routes={
        # ── Maintenance (Redis) ─────────────────────────────────────────────────
        "services.scraper.tasks.deduplicate_jobs_task": {"queue": "jh_jobs_maintenance"},
        "services.scraper.tasks.cleanup_old_jobs_task": {"queue": "jh_jobs_maintenance"},
        # ── Cover Letter / AI (Redis) ───────────────────────────────────────────
        "services.ai.tasks.fill_missing_covers_task":  {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.refresh_cover_letters_task": {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.score_job_task":             {"queue": "jh_cover_letter_bulk"},
        "services.ai.tasks.rank_jobs_task":             {"queue": "jh_cover_letter_ranking"},
        "services.ai.tasks.generate_cover_letter_task": {"queue": "jh_cover_letter_generation"},
        "services.ai.tasks.generate_embedding_task":    {"queue": "jh_embeddings"},
        "services.ai.tasks.enqueue_cover_letter_task":  {"queue": "jh_cover_letter_batch"},
        "services.ai.tasks.flush_cover_batch_task":     {"queue": "jh_cover_letter_batch"},
        # ── Email (Redis) ─────────────────────────────────────────────────────
        "services.sender.tasks.send_application_email_task": {"queue": "jh_email_send"},
        "services.sender.tasks.retry_failed_sends_task": {"queue": "jh_email_retry"},
        "services.sender.tasks.dispatch_ready_to_send_task": {"queue": "jh_email_send"},
        "services.sender.tasks.auto_approve_pending_jobs_task": {"queue": "jh_email_send"},
    },
    # Redis beat scheduler schedule.
    # fill_missing_covers and refresh_cover_letters are NOT listed here —
    # they're already in scraper/celery_app.py beat_schedule. Having them in
    # both schedulers wastes Redis round-trips (cron_safe deduplication catches
    # it, but the extra scheduling overhead is avoidable).
    beat_schedule={
        "backfill-hr-emails-every-15min": {
            "task": "services.scraper.tasks.backfill_hr_emails_task",
            "schedule": settings.beat_backfill_interval,
        },
        "cover-ready-hr-fetch-every-5min": {
            "task": "services.scraper.tasks.cover_ready_hr_fetch_task",
            "schedule": settings.beat_cover_ready_hr_interval,
        },
        # DISABLED — auto-send is turned off globally via AUTO_SEND_ENABLED=False.
        # Uncomment to re-enable automatic email sending.
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
        "cleanup-old-jobs-weekly": {
            "task": "services.scraper.tasks.cleanup_old_jobs_task",
            "schedule": settings.beat_cleanup_interval,
        },
        "fix-placeholder-emails-every-30min": {
            "task": "services.scraper.tasks.fix_placeholder_emails_task",
            "schedule": settings.beat_fix_placeholder_interval,
        },
        "deduplicate-jobs-every-5min": {
            "task": "services.scraper.tasks.deduplicate_jobs_task",
            "schedule": settings.beat_deduplicate_interval,
        },
    },
)
