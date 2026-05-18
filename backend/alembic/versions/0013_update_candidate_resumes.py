"""Update candidates with R2 resume URLs

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-06 00:00:00.000000

Updates existing candidate profiles with resume URLs from Cloudflare R2.
"""
from alembic import op
from sqlalchemy import text

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

# R2 bucket resume URLs - update these with your actual R2 public URL
R2_BASE_URL = "https://pub-8c0ae864a440df58cc57899a1e37d71f.r2.dev/job-automation"

CANDIDATE_RESUMES = [
    {
        "email": "shetty44444@gmail.com",
        "resume_url": f"{R2_BASE_URL}/suraj-shetty-software-engineer.pdf"
    },
    {
        "email": "gunjanap2018@gmail.com",
        "resume_url": f"{R2_BASE_URL}/gunjan-pandey-software-engineer.pdf"
    }
]


def upgrade() -> None:
    conn = op.get_bind()
    updated = []

    for candidate in CANDIDATE_RESUMES:
        result = conn.execute(
            text("""
                UPDATE candidates 
                SET resume_url = :resume_url 
                WHERE email = :email
                RETURNING id, name
            """),
            {"email": candidate["email"], "resume_url": candidate["resume_url"]}
        ).fetchone()

        if result:
            updated.append(f"{result[1]} ({candidate['email']})")

    if updated:
        print(f"\n✓ Resume URLs updated for: {', '.join(updated)}\n")
    else:
        print(f"\nℹ No candidates found to update\n")


def downgrade() -> None:
    conn = op.get_bind()

    emails = [c["email"] for c in CANDIDATE_RESUMES]
    conn.execute(
        text("UPDATE candidates SET resume_url = NULL WHERE email = ANY(:emails)"),
        {"emails": emails}
    )

    print(f"\n✓ Resume URLs cleared for: {', '.join(emails)}\n")
