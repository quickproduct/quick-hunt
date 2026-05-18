"""Add performance indexes across all tables.

Targets the most common query patterns observed in routers and Celery tasks:
  - jobs: tenant+status filter (dashboard), HR discovery backfill, candidate-scoped queries
  - send_logs: dedup check (job+candidate+status), candidate history
  - candidates: active-candidate listing for scheduled scrape
  - notifications: unread fetch per user
  - search_tasks: recent/pending task listing
  - usage_logs: tenant+date range usage queries
  - blacklisted_companies: name lookup

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── jobs ──────────────────────────────────────────────────────────────────

    # (tenant_id, status) — almost every dashboard/list query filters on both
    op.create_index("ix_jobs_tenant_status", "jobs", ["tenant_id", "status"], if_not_exists=True)

    # (hr_email_discovery_status) — used by reset-email-discovery and stats
    op.create_index("ix_jobs_hr_discovery_status", "jobs", ["hr_email_discovery_status"], if_not_exists=True)

    # (hr_email_discovery_attempts) — WHERE attempts < 5 in backfill queries
    op.create_index("ix_jobs_hr_discovery_attempts", "jobs", ["hr_email_discovery_attempts"], if_not_exists=True)

    # (cover_letter_generated_at) — cover generation workflow queries
    op.create_index("ix_jobs_cover_letter_generated_at", "jobs", ["cover_letter_generated_at"], if_not_exists=True)

    # (tenant_id, candidate_id) — jobs per candidate per tenant
    op.create_index("ix_jobs_tenant_candidate", "jobs", ["tenant_id", "candidate_id"], if_not_exists=True)

    # (company) — search/filter by company name
    op.create_index("ix_jobs_company", "jobs", ["company"], if_not_exists=True)

    # Partial — general backfill query: hr_email IS NULL + status not terminal + attempts < 5
    # Covers the WHERE clause in backfill_hr_emails_task exactly
    op.create_index(
        "ix_jobs_backfill_pending",
        "jobs",
        ["hr_email_discovery_attempts", "scraped_at"],
        postgresql_where="hr_email IS NULL AND status NOT IN ('sent','bounced','ignored','error')",
    )

    # (status, candidate_id) — dispatch_ready_to_send_task and workflow queries
    op.create_index("ix_jobs_status_candidate", "jobs", ["status", "candidate_id"], if_not_exists=True)

    # ── send_logs ─────────────────────────────────────────────────────────────

    # candidate_id — missing entirely; needed for candidate send history
    op.create_index("ix_send_logs_candidate_id", "send_logs", ["candidate_id"], if_not_exists=True)

    # (job_id, candidate_id, status) — dedup check in send.py:
    # WHERE job_id=X AND candidate_id=Y AND status='sent'
    op.create_index(
        "ix_send_logs_job_candidate_status",
        "send_logs",
        ["job_id", "candidate_id", "status"],
    )

    # (tenant_id, sent_at) — tenant-scoped send history with date filter
    op.create_index("ix_send_logs_tenant_sent_at", "send_logs", ["tenant_id", "sent_at"])

    # Partial — retry task: WHERE status IN ('soft_bounce','queued') fast scan
    op.create_index(
        "ix_send_logs_retry_pending",
        "send_logs",
        ["sent_at"],
        postgresql_where="status IN ('soft_bounce', 'queued')",
    )

    # ── candidates ───────────────────────────────────────────────────────────

    # (is_active) — scheduled_scrape fetches all active candidates
    op.create_index("ix_candidates_is_active", "candidates", ["is_active"], if_not_exists=True)

    # (tenant_id, is_active) — tenant-scoped active candidate list
    op.create_index("ix_candidates_tenant_active", "candidates", ["tenant_id", "is_active"])

    # ── notifications ─────────────────────────────────────────────────────────

    # (user_id, is_read) — fetch unread notification count per user
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])

    # (created_at) — order notifications by recency
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])

    # ── search_tasks ─────────────────────────────────────────────────────────

    # (created_at) — recent task listing
    op.create_index("ix_search_tasks_created_at", "search_tasks", ["created_at"], if_not_exists=True)

    # (status, created_at) — pending/running task listing
    op.create_index(
        "ix_search_tasks_status_created_at", "search_tasks", ["status", "created_at"]
    )

    # ── usage_logs ────────────────────────────────────────────────────────────

    # (tenant_id, created_at) — date-ranged usage per tenant
    op.create_index(
        "ix_usage_logs_tenant_created_at", "usage_logs", ["tenant_id", "created_at"]
    )

    # (action_type) — filter usage by action type
    op.create_index("ix_usage_logs_action_type", "usage_logs", ["action_type"])

    # ── blacklisted_companies ─────────────────────────────────────────────────

    # (name) — ILIKE search on company name during blacklist check
    op.create_index("ix_blacklisted_companies_name", "blacklisted_companies", ["name"])


def downgrade() -> None:
    op.drop_index("ix_blacklisted_companies_name", table_name="blacklisted_companies")
    op.drop_index("ix_usage_logs_action_type", table_name="usage_logs")
    op.drop_index("ix_usage_logs_tenant_created_at", table_name="usage_logs")
    op.drop_index("ix_search_tasks_status_created_at", table_name="search_tasks")
    op.drop_index("ix_search_tasks_created_at", table_name="search_tasks")
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_user_read", table_name="notifications")
    op.drop_index("ix_candidates_tenant_active", table_name="candidates")
    op.drop_index("ix_candidates_is_active", table_name="candidates")
    op.drop_index("ix_send_logs_retry_pending", table_name="send_logs")
    op.drop_index("ix_send_logs_tenant_sent_at", table_name="send_logs")
    op.drop_index("ix_send_logs_job_candidate_status", table_name="send_logs")
    op.drop_index("ix_send_logs_candidate_id", table_name="send_logs")
    op.drop_index("ix_jobs_status_candidate", table_name="jobs")
    op.drop_index("ix_jobs_backfill_pending", table_name="jobs")
    op.drop_index("ix_jobs_company", table_name="jobs")
    op.drop_index("ix_jobs_tenant_candidate", table_name="jobs")
    op.drop_index("ix_jobs_cover_letter_generated_at", table_name="jobs")
    op.drop_index("ix_jobs_hr_discovery_attempts", table_name="jobs")
    op.drop_index("ix_jobs_hr_discovery_status", table_name="jobs")
    op.drop_index("ix_jobs_tenant_status", table_name="jobs")
