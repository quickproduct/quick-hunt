"""Seed admin user with full owner access.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-13 00:00:00.000000

Creates:
  - Tenant: "Admin" (slug: admin), plan: pro
  - User: admin@gmail.com with a deployment-specific bootstrap password
  - Membership: owner on the admin tenant
"""
import os
import secrets

from alembic import op
from sqlalchemy import text

from services.api.core.security import hash_password

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_USER_ID   = "00000000-0000-0000-0000-000000000020"
ADMIN_MEMBER_ID = "00000000-0000-0000-0000-000000000030"

ADMIN_EMAIL    = "admin@gmail.com"


def upgrade() -> None:
    conn = op.get_bind()
    configured_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if configured_password and len(configured_password) < 16:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 16 characters")
    admin_password = configured_password or secrets.token_urlsafe(24)
    admin_is_active = bool(configured_password)

    # ── 1. Tenant ─────────────────────────────────────────────────────────────
    conn.execute(
        text("""
            INSERT INTO tenants (id, name, slug, plan, status, requires_approval, auto_send)
            VALUES (:id, 'Admin', 'admin', 'pro', 'active', false, false)
            ON CONFLICT (id) DO NOTHING
        """),
        {"id": ADMIN_TENANT_ID},
    )

    # ── 2. User ───────────────────────────────────────────────────────────────
    conn.execute(
        text("""
            INSERT INTO users (id, tenant_id, email, hashed_password, role, is_verified, is_active)
            VALUES (:id, :tenant_id, :email, :hashed_password, 'owner', true, :is_active)
            ON CONFLICT DO NOTHING
        """),
        {
            "id": ADMIN_USER_ID,
            "tenant_id": ADMIN_TENANT_ID,
            "email": ADMIN_EMAIL,
            "hashed_password": hash_password(admin_password),
            "is_active": admin_is_active,
        },
    )

    # ── 3. Membership ─────────────────────────────────────────────────────────
    conn.execute(
        text("""
            INSERT INTO memberships (id, user_id, tenant_id, role)
            VALUES (:id, :user_id, :tenant_id, 'owner')
            ON CONFLICT DO NOTHING
        """),
        {
            "id": ADMIN_MEMBER_ID,
            "user_id": ADMIN_USER_ID,
            "tenant_id": ADMIN_TENANT_ID,
        },
    )

    print("\n✓ Admin user seeded")
    print(f"  Email:    {ADMIN_EMAIL}")
    if configured_password:
        print("  Credential: supplied through INITIAL_ADMIN_PASSWORD")
    else:
        print("  Account disabled: set INITIAL_ADMIN_PASSWORD before migration to enable it")
    print(f"  Role:     owner")
    print(f"  Tenant:   Admin (id={ADMIN_TENANT_ID})\n")


def downgrade() -> None:
    conn = op.get_bind()

    conn.execute(
        text("DELETE FROM memberships WHERE id = :id"),
        {"id": ADMIN_MEMBER_ID},
    )
    conn.execute(
        text("DELETE FROM users WHERE id = :id"),
        {"id": ADMIN_USER_ID},
    )
    conn.execute(
        text("DELETE FROM tenants WHERE id = :id"),
        {"id": ADMIN_TENANT_ID},
    )

    print("\n✓ Admin user removed\n")
