"""Track queued and failed direct HR sends.

Revision ID: 0032
Revises: 0031
"""
import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "direct_send_logs",
        sa.Column("status", sa.String(30), nullable=False, server_default="sent"),
    )
    op.add_column("direct_send_logs", sa.Column("provider", sa.String(30), nullable=True))
    op.add_column("direct_send_logs", sa.Column("provider_message_id", sa.String(200), nullable=True))
    op.add_column("direct_send_logs", sa.Column("celery_task_id", sa.String(200), nullable=True))
    op.add_column("direct_send_logs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column("direct_send_logs", sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()))
    op.add_column("direct_send_logs", sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()))
    op.alter_column("direct_send_logs", "sent_at", existing_type=sa.DateTime(), server_default=None)
    op.execute("UPDATE direct_send_logs SET created_at = COALESCE(sent_at, created_at)")
    op.create_index("ix_direct_send_logs_status", "direct_send_logs", ["status"])
    op.create_index("ix_direct_send_logs_celery_task_id", "direct_send_logs", ["celery_task_id"])


def downgrade() -> None:
    op.drop_index("ix_direct_send_logs_celery_task_id", table_name="direct_send_logs")
    op.drop_index("ix_direct_send_logs_status", table_name="direct_send_logs")
    op.alter_column("direct_send_logs", "sent_at", existing_type=sa.DateTime(), server_default=sa.func.now())
    op.drop_column("direct_send_logs", "updated_at")
    op.drop_column("direct_send_logs", "created_at")
    op.drop_column("direct_send_logs", "error_message")
    op.drop_column("direct_send_logs", "celery_task_id")
    op.drop_column("direct_send_logs", "provider_message_id")
    op.drop_column("direct_send_logs", "provider")
    op.drop_column("direct_send_logs", "status")
