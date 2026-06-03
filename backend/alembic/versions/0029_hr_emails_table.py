"""Add hr_emails deduplication registry table.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-19 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hr_emails",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("email", sa.String(300), nullable=False),
        sa.Column("domain", sa.String(200), nullable=False),
        sa.Column("job_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("send_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("delivered_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("opened_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("clicked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("hard_bounce_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("soft_bounce_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("spam_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_send_at", sa.DateTime, nullable=True),
        sa.Column("last_bounce_at", sa.DateTime, nullable=True),
        sa.Column("last_bounce_type", sa.String(20), nullable=True),
        sa.Column("last_bounce_reason", sa.Text, nullable=True),
        sa.Column("mx_valid", sa.Boolean, nullable=True),
        sa.Column("mx_checked_at", sa.DateTime, nullable=True),
        sa.Column("validation_status", sa.String(20), nullable=False, server_default="unknown"),
        sa.Column("is_placeholder", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_hr_emails_tenant_email", "hr_emails", ["tenant_id", "email"]
    )
    op.create_index("ix_hr_emails_tenant_id", "hr_emails", ["tenant_id"])
    op.create_index("ix_hr_emails_domain", "hr_emails", ["domain"])
    op.create_index("ix_hr_emails_validation_status", "hr_emails", ["validation_status"])
    op.create_index("ix_hr_emails_tenant_domain", "hr_emails", ["tenant_id", "domain"])
    op.create_index("ix_hr_emails_last_bounce_at", "hr_emails", ["last_bounce_at"])


def downgrade() -> None:
    op.drop_index("ix_hr_emails_last_bounce_at", table_name="hr_emails")
    op.drop_index("ix_hr_emails_tenant_domain", table_name="hr_emails")
    op.drop_index("ix_hr_emails_validation_status", table_name="hr_emails")
    op.drop_index("ix_hr_emails_domain", table_name="hr_emails")
    op.drop_index("ix_hr_emails_tenant_id", table_name="hr_emails")
    op.drop_constraint("uq_hr_emails_tenant_email", "hr_emails", type_="unique")
    op.drop_table("hr_emails")
