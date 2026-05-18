"""Add score_breakdown column to jobs table

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-25 00:00:00.000000

New job status lifecycle (string column, no DB constraint):
  new → filtered → scoring → cover_generated → pending_approval → sending → sent
                                                                 ↘ ignored (rejected by user)
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("score_breakdown", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jobs", "score_breakdown")
