"""Remove 'ignored' job status: convert to 'new', update partial index.

Revision ID: 0026
Revises: 0025
Create Date: 2026-05-06
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Convert any remaining ignored jobs to new (idempotent)
    op.execute("UPDATE jobs SET status = 'new' WHERE status = 'ignored'")

    # 2. Recreate the partial index without 'ignored'
    op.execute("DROP INDEX IF EXISTS ix_jobs_backfill_pending")
    op.execute(
        """
        CREATE INDEX ix_jobs_backfill_pending
        ON jobs (hr_email_discovery_attempts, scraped_at)
        WHERE hr_email IS NULL
          AND status NOT IN ('sent', 'bounced', 'error')
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_jobs_backfill_pending")
    op.execute(
        """
        CREATE INDEX ix_jobs_backfill_pending
        ON jobs (hr_email_discovery_attempts, scraped_at)
        WHERE hr_email IS NULL
          AND status NOT IN ('sent', 'bounced', 'ignored', 'error')
        """
    )
