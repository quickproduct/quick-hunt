"""Create sentinel tenant and backfill tenant_id on all business tables,
then make tenant_id NOT NULL.

Sentinel tenant: 00000000-0000-0000-0000-000000000001
Used for backward-compat X-API-Key requests.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

SENTINEL_ID = "00000000-0000-0000-0000-000000000001"
SENTINEL_SLUG = "default"


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Insert sentinel tenant ─────────────────────────────────────────
    conn.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan, status) "
            "VALUES (:id, :name, :slug, 'free', 'active') "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": SENTINEL_ID, "name": "Default", "slug": SENTINEL_SLUG},
    )

    # ── 2. Backfill all nullable tenant_id columns ────────────────────────
    for table in ("candidates", "jobs", "embeddings", "send_logs", "search_tasks"):
        conn.execute(
            sa.text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
            {"tid": SENTINEL_ID},
        )

    # ── 3. Make tenant_id NOT NULL ────────────────────────────────────────
    for table in ("candidates", "jobs", "embeddings", "send_logs", "search_tasks"):
        op.alter_column(table, "tenant_id", nullable=False)


def downgrade() -> None:
    for table in ("candidates", "jobs", "embeddings", "send_logs", "search_tasks"):
        op.alter_column(table, "tenant_id", nullable=True)
    # Do not delete the sentinel tenant on downgrade (data safety)
