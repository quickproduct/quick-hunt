"""Switch candidate resume_url from R2 HTTP URLs to local paths.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-09

Replaces the Cloudflare R2 public URLs with local relative paths of the form
"resumes/<filename>.pdf".  The new resume_fetcher.py reads directly from
backend/resumes/ so no cloud bucket is needed.
"""
from alembic import op
from sqlalchemy import text

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

# Map candidate email → local resume filename
RESUME_MAP = [
    {
        "email": "srshetty@surajshetty.online",
        "resume_url": "resumes/suraj-shetty-software-engineer.pdf",
    },
    {
        "email": "gunjanpandey@quickspin.cloud",
        "resume_url": "resumes/gunjan-pandey-software-engineer.pdf",
    },
]


def upgrade() -> None:
    conn = op.get_bind()
    updated = []
    for entry in RESUME_MAP:
        row = conn.execute(
            text("""
                UPDATE candidates
                SET resume_url = :resume_url
                WHERE email = :email
                RETURNING name
            """),
            {"email": entry["email"], "resume_url": entry["resume_url"]},
        ).fetchone()
        if row:
            updated.append(f"{row[0]} → {entry['resume_url']}")

    if updated:
        print(f"\n✓ Resume paths updated:\n  " + "\n  ".join(updated) + "\n")
    else:
        print("\nℹ No matching candidates found — check emails in RESUME_MAP\n")


def downgrade() -> None:
    R2_BASE = "https://pub-8c0ae864a440df58cc57899a1e37d71f.r2.dev/job-automation"
    conn = op.get_bind()
    for entry in RESUME_MAP:
        filename = entry["resume_url"].split("/")[-1]
        conn.execute(
            text("UPDATE candidates SET resume_url = :url WHERE email = :email"),
            {"email": entry["email"], "url": f"{R2_BASE}/{filename}"},
        )

