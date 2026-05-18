"""Add HR email discovery tracking columns.

Adds hr_email_discovery_status, hr_email_discovery_attempts, and
hr_email_discovered_at to the jobs table so the backfill pipeline can
skip jobs that have exhausted their discovery attempts instead of
retrying them indefinitely.

Also adds a partial composite index optimising the cover_ready_hr_fetch
query: WHERE status='cover_generated' AND hr_email IS NULL.

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("hr_email_discovery_status", sa.String(30), nullable=True)
    )
    op.add_column(
        "jobs",
        sa.Column("hr_email_discovery_attempts", sa.Integer(), nullable=True, server_default="0")
    )
    op.add_column(
        "jobs",
        sa.Column("hr_email_discovered_at", sa.TIMESTAMP(), nullable=True)
    )

    # Backfill existing rows — jobs that already have an HR email are 'found';
    # jobs without one that are still active are 'pending'.
    op.execute("""
        UPDATE jobs
        SET hr_email_discovery_status = 'found',
            hr_email_discovered_at = COALESCE(scraped_at, NOW())
        WHERE hr_email IS NOT NULL
          AND hr_email_discovery_status IS NULL
    """)
    op.execute("""
        UPDATE jobs
        SET hr_email_discovery_status = 'pending',
            hr_email_discovery_attempts = 0
        WHERE hr_email IS NULL
          AND hr_email_discovery_status IS NULL
          AND status NOT IN ('filtered', 'ignored', 'sent', 'bounced', 'error')
    """)

    # Partial composite index for the hottest HR-email-discovery query.
    op.create_index(
        "ix_jobs_hr_discovery_cover_ready",
        "jobs",
        ["hr_email_discovery_attempts", "scraped_at"],
        postgresql_where="hr_email IS NULL AND status = 'cover_generated'",
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_jobs_hr_discovery_cover_ready",
        table_name="jobs",
        if_exists=True,
    )
    op.drop_column("jobs", "hr_email_discovered_at", if_exists=True)
    op.drop_column("jobs", "hr_email_discovery_attempts", if_exists=True)
    op.drop_column("jobs", "hr_email_discovery_status", if_exists=True)
