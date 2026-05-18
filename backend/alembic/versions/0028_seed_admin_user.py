"""Seed admin user with full owner access.

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-13 00:00:00.000000

Creates:
  - Tenant: "Admin" (slug: admin), plan: pro
  - User: admin@gmail.com / admin@123, role: owner, pre-verified
  - Membership: owner on the admin tenant
"""
from alembic import op
from sqlalchemy import text

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None

ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_USER_ID   = "00000000-0000-0000-0000-000000000020"
ADMIN_MEMBER_ID = "00000000-0000-0000-0000-000000000030"

ADMIN_EMAIL    = "admin@gmail.com"
# bcrypt hash of "admin@123" (cost 12)
ADMIN_HASH     = "$2b$12$jIRJMndIjoMoOzeMAGwV/eLWyDablUILUULSLjrkw43xSMNrUoLcS"


def upgrade() -> None:
    conn = op.get_bind()

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
            VALUES (:id, :tenant_id, :email, :hashed_password, 'owner', true, true)
            ON CONFLICT DO NOTHING
        """),
        {
            "id": ADMIN_USER_ID,
            "tenant_id": ADMIN_TENANT_ID,
            "email": ADMIN_EMAIL,
            "hashed_password": ADMIN_HASH,
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
    print(f"  Password: admin@123")
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
