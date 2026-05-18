"""Add performance indexes for common filter/sort patterns

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-21 00:00:00.000000
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Single-column functional/partial indexes ──────────────────────────────
    # Used by stats endpoint: COUNT(*) WHERE hr_email IS NOT NULL
    op.create_index(
        "ix_jobs_hr_email_notnull",
        "jobs",
        ["hr_email"],
        postgresql_where="hr_email IS NOT NULL",
    )
    # Used by stats endpoint: COUNT(*) WHERE cover_letter IS NOT NULL
    op.create_index(
        "ix_jobs_cover_letter_notnull",
        "jobs",
        ["cover_letter"],
        postgresql_where="cover_letter IS NOT NULL",
    )
    # Used as default sort column on list_jobs
    op.create_index("ix_jobs_scraped_at", "jobs", ["scraped_at"])
    # Used by min_score / max_score filters and sort
    op.create_index("ix_jobs_relevance_score", "jobs", ["relevance_score"])

    # ── Composite indexes for common filter + sort combos ─────────────────────
    # list_jobs default: WHERE status=? ORDER BY scraped_at DESC
    op.create_index(
        "ix_jobs_status_scraped_at",
        "jobs",
        ["status", "scraped_at"],
    )
    # "Ready to Apply" preset: WHERE hr_email IS NOT NULL AND cover_letter IS NOT NULL
    op.create_index(
        "ix_jobs_hr_cover_status",
        "jobs",
        ["hr_email", "cover_letter", "status"],
        postgresql_where="hr_email IS NOT NULL AND cover_letter IS NOT NULL",
    )
    # backfill task: WHERE hr_email IS NULL AND status NOT IN (...)
    op.create_index(
        "ix_jobs_hr_email_null",
        "jobs",
        ["hr_email"],
        postgresql_where="hr_email IS NULL",
    )
    # send_logs sorted by sent_at for the logs page
    op.create_index("ix_send_logs_sent_at", "send_logs", ["sent_at"])


def downgrade() -> None:
    op.drop_index("ix_send_logs_sent_at", table_name="send_logs")
    op.drop_index("ix_jobs_hr_email_null", table_name="jobs")
    op.drop_index("ix_jobs_hr_cover_status", table_name="jobs")
    op.drop_index("ix_jobs_status_scraped_at", table_name="jobs")
    op.drop_index("ix_jobs_relevance_score", table_name="jobs")
    op.drop_index("ix_jobs_scraped_at", table_name="jobs")
    op.drop_index("ix_jobs_cover_letter_notnull", table_name="jobs")
    op.drop_index("ix_jobs_hr_email_notnull", table_name="jobs")
