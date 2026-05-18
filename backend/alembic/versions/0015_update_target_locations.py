"""Update candidate target locations to include India and all major cities

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-07 00:00:00.000000

Updates target_locations for existing candidates to include:
- India (for all-India job searches covering onsite, hybrid, remote)
- Additional major cities: Pune, Chennai, Delhi, Gurgaon, Noida
"""
from alembic import op
from sqlalchemy import text
import json

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

# Admin tenant ID
ADMIN_TENANT_ID = "00000000-0000-0000-0000-000000000001"

# Updated target locations - includes India for all-India job searches
NEW_TARGET_LOCATIONS = ["India", "Bangalore", "Remote", "Mumbai", "Hyderabad", "Pune", "Chennai", "Delhi", "Gurgaon", "Noida"]

# Candidate emails to update
CANDIDATE_EMAILS = ["shetty44444@gmail.com", "gunjanap2018@gmail.com"]


def upgrade() -> None:
    conn = op.get_bind()

    for email in CANDIDATE_EMAILS:
        # Check if candidate exists
        result = conn.execute(
            text("SELECT id, target_locations FROM candidates WHERE email = :email AND tenant_id = :tenant_id"),
            {"email": email, "tenant_id": ADMIN_TENANT_ID}
        ).fetchone()

        if result:
            candidate_id = result[0]
            current_locations = result[1] or []

            # Update target_locations
            conn.execute(
                text("""
                    UPDATE candidates
                    SET target_locations = (:target_locations)::jsonb,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": candidate_id,
                    "target_locations": json.dumps(NEW_TARGET_LOCATIONS),
                }
            )
            print(f"✓ Updated target_locations for {email}: {NEW_TARGET_LOCATIONS}")
        else:
            print(f"ℹ Candidate not found: {email}")


def downgrade() -> None:
    conn = op.get_bind()

    # Restore original locations
    original_locations = ["Bangalore", "Remote", "Mumbai", "Hyderabad"]

    for email in CANDIDATE_EMAILS:
        result = conn.execute(
            text("SELECT id FROM candidates WHERE email = :email AND tenant_id = :tenant_id"),
            {"email": email, "tenant_id": ADMIN_TENANT_ID}
        ).fetchone()

        if result:
            candidate_id = result[0]
            conn.execute(
                text("""
                    UPDATE candidates
                    SET target_locations = (:target_locations)::jsonb,
                        updated_at = NOW()
                    WHERE id = :id
                """),
                {
                    "id": candidate_id,
                    "target_locations": json.dumps(original_locations),
                }
            )
            print(f"✓ Restored target_locations for {email}: {original_locations}")
