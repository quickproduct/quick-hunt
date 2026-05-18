"""Add tasks_total and tasks_completed to search_tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-18 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("search_tasks", sa.Column("tasks_total", sa.Integer, server_default="0"))
    op.add_column("search_tasks", sa.Column("tasks_completed", sa.Integer, server_default="0"))


def downgrade() -> None:
    op.drop_column("search_tasks", "tasks_completed")
    op.drop_column("search_tasks", "tasks_total")
