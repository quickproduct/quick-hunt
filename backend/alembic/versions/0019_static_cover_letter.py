"""Add static_cover_letter to candidates.

Used by the Direct HR Send feature — a fixed cover letter (no dynamic
placeholders) sent directly to a list of HR email addresses without
needing a job posting. Stored per-candidate so it only needs to be
written once.

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "candidates",
        sa.Column("static_cover_letter", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("candidates", "static_cover_letter")
