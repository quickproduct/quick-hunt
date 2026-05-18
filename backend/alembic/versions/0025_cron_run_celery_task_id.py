"""Add celery_task_id to cron_runs.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cron_runs", sa.Column("celery_task_id", sa.String(length=200), nullable=True))
    op.create_index("ix_cron_runs_celery_task_id", "cron_runs", ["celery_task_id"])


def downgrade() -> None:
    op.drop_index("ix_cron_runs_celery_task_id", table_name="cron_runs")
    op.drop_column("cron_runs", "celery_task_id")
