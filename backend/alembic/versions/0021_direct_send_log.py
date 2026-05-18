"""Add direct_send_logs table for deduplication of direct HR sends.

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "direct_send_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("hr_email", sa.String(300), nullable=False),
        sa.Column("sent_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "candidate_id", "hr_email",
            name="uq_direct_send_tenant_candidate_email",
        ),
    )
    op.create_index(
        "ix_direct_send_logs_tenant_candidate",
        "direct_send_logs",
        ["tenant_id", "candidate_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_direct_send_logs_tenant_candidate", table_name="direct_send_logs")
    op.drop_table("direct_send_logs")
