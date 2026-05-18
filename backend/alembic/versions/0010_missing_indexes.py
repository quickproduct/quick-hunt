"""Add missing indexes for search_tasks, send_logs, candidates

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-01 00:00:00.000000

Fixes three full-table sequential scans on hot query paths:
  - search_tasks.created_at  — ORDER BY DESC in list_search_tasks
  - send_logs.candidate_id   — WHERE in bulk_send duplicate check
  - candidates.is_active     — WHERE is_active = true in candidate list
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_search_tasks_created_at", "search_tasks", ["created_at"])
    op.create_index("ix_send_logs_candidate_id", "send_logs", ["candidate_id"])
    op.create_index("ix_candidates_is_active", "candidates", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_candidates_is_active", table_name="candidates")
    op.drop_index("ix_send_logs_candidate_id", table_name="send_logs")
    op.drop_index("ix_search_tasks_created_at", table_name="search_tasks")
