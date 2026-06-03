"""Create mnc_companies table and seed from hardcoded MNC_COMPANIES list.

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-21
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

SENTINEL_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.create_table(
        "mnc_companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("career_url", sa.String(1000), nullable=False),
        sa.Column("ats", sa.String(40), nullable=False, server_default="custom"),
        sa.Column("ats_slug", sa.String(200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mnc_companies_tenant_name"),
    )
    op.create_index("ix_mnc_companies_tenant_id", "mnc_companies", ["tenant_id"])
    op.create_index("ix_mnc_companies_name", "mnc_companies", ["name"])
    op.create_index("ix_mnc_companies_active", "mnc_companies", ["active"])

    # Seed the hardcoded MNC company list into the sentinel tenant.
    # Imported here (not at module top) so the migration stays importable
    # even if the scraper package layout changes later.
    from services.scraper.mnc_companies import MNC_COMPANIES

    seed_table = sa.table(
        "mnc_companies",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("name", sa.String),
        sa.column("career_url", sa.String),
        sa.column("ats", sa.String),
        sa.column("ats_slug", sa.String),
        sa.column("active", sa.Boolean),
    )

    # De-duplicate by name on the way in (defensive — the unique constraint
    # would catch this but cleaner to skip silently than abort the migration).
    seen: set[str] = set()
    rows = []
    for c in MNC_COMPANIES:
        name = (c.get("name") or "").strip()
        career_url = (c.get("career_url") or "").strip()
        if not name or not career_url:
            continue
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        rows.append({
            "id": str(uuid.uuid4()),
            "tenant_id": SENTINEL_TENANT_ID,
            "name": name,
            "career_url": career_url,
            "ats": c.get("ats", "custom") or "custom",
            "ats_slug": c.get("ats_slug") or None,
            "active": True,
        })

    if rows:
        op.bulk_insert(seed_table, rows)


def downgrade() -> None:
    op.drop_index("ix_mnc_companies_active", table_name="mnc_companies")
    op.drop_index("ix_mnc_companies_name", table_name="mnc_companies")
    op.drop_index("ix_mnc_companies_tenant_id", table_name="mnc_companies")
    op.drop_table("mnc_companies")
