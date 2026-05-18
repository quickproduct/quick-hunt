"""Update candidate email addresses

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-07 00:00:00.000000

Updates existing candidate email addresses:
  - Suraj Shetty: shetty44444@gmail.com → srshetty@surajshetty.online
  - Gunjan Pandey: gunjanap2018@gmail.com → gunjanpandey@quickspin.cloud
"""
from alembic import op
from sqlalchemy import text

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

EMAIL_UPDATES = [
    {
        "old_email": "shetty44444@gmail.com",
        "new_email": "srshetty@surajshetty.online",
        "name": "Suraj Shetty"
    },
    {
        "old_email": "gunjanap2018@gmail.com",
        "new_email": "gunjanpandey@quickspin.cloud",
        "name": "Gunjan Pandey"
    }
]


def upgrade() -> None:
    conn = op.get_bind()
    updated = []

    for update in EMAIL_UPDATES:
        result = conn.execute(
            text("""
                UPDATE candidates 
                SET email = :new_email 
                WHERE email = :old_email
                RETURNING id, name
            """),
            {"old_email": update["old_email"], "new_email": update["new_email"]}
        ).fetchone()

        if result:
            updated.append(f"{result[1]}: {update['old_email']} → {update['new_email']}")

    if updated:
        updates_str = "\n  - ".join(updated)
        print(f"\n✓ Email addresses updated:\n  - {updates_str}\n")
    else:
        print(f"\nℹ No candidates found to update\n")


def downgrade() -> None:
    conn = op.get_bind()
    reverted = []

    for update in EMAIL_UPDATES:
        result = conn.execute(
            text("""
                UPDATE candidates 
                SET email = :old_email 
                WHERE email = :new_email
                RETURNING id, name
            """),
            {"old_email": update["old_email"], "new_email": update["new_email"]}
        ).fetchone()

        if result:
            reverted.append(f"{result[1]}: {update['new_email']} → {update['old_email']}")

    if reverted:
        reverts_str = "\n  - ".join(reverted)
        print(f"\n✓ Email addresses reverted:\n  - {reverts_str}\n")
    else:
        print(f"\nℹ No candidates found to revert\n")
