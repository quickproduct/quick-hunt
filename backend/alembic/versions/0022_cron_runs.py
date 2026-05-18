"""Add cron_runs table for cron task execution history.

Revision ID: 0022
Revises: 0021_direct_send_log
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cron_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_name", sa.String(200), nullable=False),
        sa.Column("started_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("error_summary", sa.String(500), nullable=True),
        sa.Column("error_traceback", sa.Text, nullable=True),
        sa.Column("pre_state", sa.JSON, nullable=True),
        sa.Column("post_state", sa.JSON, nullable=True),
        sa.Column("steps", sa.JSON, nullable=True),
        sa.Column("triggered_by", sa.String(20), nullable=False, server_default="beat"),
        sa.Column("worker_host", sa.String(200), nullable=True),
    )
    op.create_index("ix_cron_runs_task_started", "cron_runs", ["task_name", "started_at"])
    op.create_index("ix_cron_runs_status_started", "cron_runs", ["status", "started_at"])


def downgrade() -> None:
    op.drop_index("ix_cron_runs_status_started", table_name="cron_runs")
    op.drop_index("ix_cron_runs_task_started", table_name="cron_runs")
    op.drop_table("cron_runs")
