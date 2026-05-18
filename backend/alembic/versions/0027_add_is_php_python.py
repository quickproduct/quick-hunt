"""Add is_php_python column to jobs table.

Revision ID: 0027
Revises: 0026
Create Date: 2026-05-08
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "is_php_python",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("jobs", "is_php_python")
