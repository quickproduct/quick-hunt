"""Add jobs_old_skipped and jobs_date_unavailable to search_tasks.

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_tasks",
        sa.Column("jobs_old_skipped", sa.Integer, server_default="0", nullable=False),
    )
    op.add_column(
        "search_tasks",
        sa.Column("jobs_date_unavailable", sa.Integer, server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("search_tasks", "jobs_date_unavailable")
    op.drop_column("search_tasks", "jobs_old_skipped")
