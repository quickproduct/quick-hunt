"""Repair and rotate the seeded platform administrator.

Revision ID: 0034
Revises: 0033

The historical backup at revision 0031 contains a password hash produced by
the legacy hashing path.  Current authentication SHA-256-prehashes passwords
before bcrypt, so the administrator must be re-hashed with the current helper.
This migration also repairs the deterministic tenant and membership records.
"""
import os

from alembic import op
from sqlalchemy import text

from services.api.core.security import hash_password

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_USER_ID = "00000000-0000-0000-0000-000000000020"
ADMIN_MEMBER_ID = "00000000-0000-0000-0000-000000000030"
ADMIN_EMAIL = "admin@gmail.com"


def upgrade() -> None:
    configured_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if len(configured_password) < 16:
        raise RuntimeError(
            "INITIAL_ADMIN_PASSWORD must be configured with at least 16 characters"
        )

    conn = op.get_bind()
    conn.execute(
        text(
            """
            INSERT INTO tenants (
                id, name, slug, plan, status, requires_approval, auto_send
            )
            VALUES (
                :tenant_id, 'Admin', 'admin', 'pro', 'active', false, false
            )
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                slug = EXCLUDED.slug,
                plan = EXCLUDED.plan,
                status = EXCLUDED.status,
                requires_approval = EXCLUDED.requires_approval
            """
        ),
        {"tenant_id": ADMIN_TENANT_ID},
    )

    admin_user_id = conn.execute(
        text(
            """
            INSERT INTO users (
                id, tenant_id, email, hashed_password, role,
                is_verified, is_active, verification_token,
                reset_token, reset_token_expires
            )
            VALUES (
                :user_id, :tenant_id, :email, :hashed_password, 'owner',
                true, true, NULL, NULL, NULL
            )
            ON CONFLICT (email, tenant_id) DO UPDATE
            SET hashed_password = EXCLUDED.hashed_password,
                role = 'owner',
                is_verified = true,
                is_active = true,
                verification_token = NULL,
                reset_token = NULL,
                reset_token_expires = NULL
            RETURNING id
            """
        ),
        {
            "user_id": ADMIN_USER_ID,
            "tenant_id": ADMIN_TENANT_ID,
            "email": ADMIN_EMAIL,
            "hashed_password": hash_password(configured_password),
        },
    ).scalar_one()

    conn.execute(
        text(
            """
            INSERT INTO memberships (id, user_id, tenant_id, role)
            VALUES (:membership_id, :user_id, :tenant_id, 'owner')
            ON CONFLICT (user_id, tenant_id) DO UPDATE
            SET role = 'owner'
            """
        ),
        {
            "membership_id": ADMIN_MEMBER_ID,
            "user_id": admin_user_id,
            "tenant_id": ADMIN_TENANT_ID,
        },
    )


def downgrade() -> None:
    # Credential repair is intentionally irreversible.
    pass
