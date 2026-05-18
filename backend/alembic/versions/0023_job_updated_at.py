"""Add updated_at column to jobs table.

Revision ID: 0023
Revises: 0022_cron_runs
Create Date: 2026-04-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now(), nullable=True),
    )
    op.create_index("ix_jobs_updated_at", "jobs", ["updated_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_updated_at", table_name="jobs")
    op.drop_column("jobs", "updated_at")
