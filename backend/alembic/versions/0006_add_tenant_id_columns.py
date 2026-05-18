"""Add tenant_id (nullable) to all business tables.

Drops the global unique constraints that would block multi-tenancy
and replaces them with per-tenant unique constraints.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── candidates ─────────────────────────────────────────────────────────
    op.add_column("candidates", sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_candidates_tenant_id", "candidates", "tenants", ["tenant_id"], ["id"]
    )
    # Drop global unique index on email, replace with per-tenant unique constraint
    op.drop_index("ix_candidates_email", table_name="candidates")
    op.create_unique_constraint(
        "uq_candidates_email_tenant", "candidates", ["email", "tenant_id"]
    )
    op.create_index("ix_candidates_tenant_id", "candidates", ["tenant_id"])

    # ── jobs ───────────────────────────────────────────────────────────────
    op.add_column("jobs", sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_jobs_tenant_id", "jobs", "tenants", ["tenant_id"], ["id"]
    )
    # Drop global unique index on dedupe_hash, replace with per-tenant unique constraint
    op.drop_index("ix_jobs_dedupe_hash", table_name="jobs")
    op.create_unique_constraint(
        "uq_jobs_tenant_dedupe", "jobs", ["tenant_id", "dedupe_hash"]
    )
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])

    # ── embeddings ─────────────────────────────────────────────────────────
    op.add_column("embeddings", sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_index("ix_embeddings_tenant_id", "embeddings", ["tenant_id"])

    # ── send_logs ──────────────────────────────────────────────────────────
    op.add_column("send_logs", sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_index("ix_send_logs_tenant_id", "send_logs", ["tenant_id"])

    # ── search_tasks ───────────────────────────────────────────────────────
    op.add_column("search_tasks", sa.Column("tenant_id", sa.String(36), nullable=True))
    op.create_index("ix_search_tasks_tenant_id", "search_tasks", ["tenant_id"])


def downgrade() -> None:
    for table in ("search_tasks", "send_logs", "embeddings"):
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_column(table, "tenant_id")

    op.drop_index("ix_jobs_tenant_id", table_name="jobs")
    op.drop_constraint("uq_jobs_tenant_dedupe", "jobs", type_="unique")
    op.drop_constraint("fk_jobs_tenant_id", "jobs", type_="foreignkey")
    op.create_index("ix_jobs_dedupe_hash", "jobs", ["dedupe_hash"], unique=True)
    op.drop_column("jobs", "tenant_id")

    op.drop_index("ix_candidates_tenant_id", table_name="candidates")
    op.drop_constraint("uq_candidates_email_tenant", "candidates", type_="unique")
    op.drop_constraint("fk_candidates_tenant_id", "candidates", type_="foreignkey")
    op.create_index("ix_candidates_email", "candidates", ["email"], unique=True)
    op.drop_column("candidates", "tenant_id")
