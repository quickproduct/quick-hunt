"""Add composite index on (status, hr_email) for cover-ready HR email queries.

This index optimises the hottest query in the HR email discovery pipeline:
  SELECT ... FROM jobs WHERE status = 'cover_generated' AND hr_email IS NULL

Previously this used ix_jobs_status_scraped_at (status, scraped_at) which
required filtering hr_email IS NULL from a wider set of rows.  The new
composite index lets Postgres jump directly to cover_generated + NULL rows.

Revision ID: 0017
Revises: 0016
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_jobs_status_hr_email",
        "jobs",
        ["status", "hr_email"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_jobs_status_hr_email", table_name="jobs", if_exists=True)