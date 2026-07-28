"""Secure the historical seeded platform administrator.

Revision ID: 0033
Revises: 0032

Fresh installations receive a deployment-specific password in revision 0028.
For databases that already ran the old migration, rotate the password when
INITIAL_ADMIN_PASSWORD is available; otherwise disable only the account that
still has the published legacy hash.
"""
import os

from alembic import op
from sqlalchemy import text

from services.api.core.security import hash_password

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000002"
ADMIN_EMAIL = "admin@gmail.com"
LEGACY_ADMIN_HASH = "$2b$12$jIRJMndIjoMoOzeMAGwV/eLWyDablUILUULSLjrkw43xSMNrUoLcS"


def upgrade() -> None:
    conn = op.get_bind()
    configured_password = os.getenv("INITIAL_ADMIN_PASSWORD", "")
    if configured_password and len(configured_password) < 16:
        raise RuntimeError("INITIAL_ADMIN_PASSWORD must be at least 16 characters")

    if configured_password:
        conn.execute(
            text(
                """
                UPDATE users
                SET hashed_password = :hashed_password,
                    is_active = true,
                    reset_token = NULL,
                    reset_token_expires = NULL
                WHERE tenant_id = :tenant_id AND email = :email
                """
            ),
            {
                "hashed_password": hash_password(configured_password),
                "tenant_id": ADMIN_TENANT_ID,
                "email": ADMIN_EMAIL,
            },
        )
        return

    conn.execute(
        text(
            """
            UPDATE users
            SET is_active = false,
                reset_token = NULL,
                reset_token_expires = NULL
            WHERE tenant_id = :tenant_id
              AND email = :email
              AND hashed_password = :legacy_hash
            """
        ),
        {
            "tenant_id": ADMIN_TENANT_ID,
            "email": ADMIN_EMAIL,
            "legacy_hash": LEGACY_ADMIN_HASH,
        },
    )


def downgrade() -> None:
    # Credential hardening is intentionally irreversible.
    pass
