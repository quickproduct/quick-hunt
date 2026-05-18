"""Initial schema — creates all 5 tables

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable required extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # candidates
    op.create_table(
        "candidates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("skills", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("years_experience", sa.Integer, nullable=True),
        sa.Column("resume_url", sa.String(500), nullable=True),
        sa.Column("target_roles", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("target_locations", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("bio", sa.Text, nullable=True),
        sa.Column("linkedin_url", sa.String(300), nullable=True),
        sa.Column("github_url", sa.String(300), nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_candidates_email", "candidates", ["email"], unique=True)

    # jobs
    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=True),
        sa.Column("job_title", sa.String(300), nullable=False),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("location", sa.String(300), nullable=True),
        sa.Column("job_description", sa.Text, nullable=True),
        sa.Column("job_url", sa.String(1000), nullable=False),
        sa.Column("posted_date", sa.DateTime, nullable=True),
        sa.Column("scraped_at", sa.DateTime, server_default=sa.text("NOW()")),
        sa.Column("hr_email", sa.String(300), nullable=True),
        sa.Column("company_website", sa.String(500), nullable=True),
        sa.Column("recruiter_name", sa.String(200), nullable=True),
        sa.Column("source_portal", sa.String(50), nullable=False),
        sa.Column("status", sa.String(30), server_default="new"),
        sa.Column("dedupe_hash", sa.String(64), nullable=False),
        sa.Column("salary_min", sa.Float, nullable=True),
        sa.Column("salary_max", sa.Float, nullable=True),
        sa.Column("salary_currency", sa.String(10), nullable=True),
        sa.Column("job_type", sa.String(50), nullable=True),
        sa.Column("experience_required", sa.String(100), nullable=True),
        sa.Column("raw_data", postgresql.JSON, nullable=True),
        sa.Column("relevance_score", sa.Float, nullable=True),
        sa.Column("cover_letter", sa.Text, nullable=True),
        sa.Column("cover_letter_generated_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_jobs_dedupe_hash", "jobs", ["dedupe_hash"], unique=True)
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_index("ix_jobs_candidate_id", "jobs", ["candidate_id"])
    op.create_index("ix_jobs_source_portal", "jobs", ["source_portal"])

    # embeddings
    op.create_table(
        "embeddings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("vector_id", sa.String(200), nullable=True),
        sa.Column("embedding_source", sa.String(50), nullable=True),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("embedding_json", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_embeddings_job_id", "embeddings", ["job_id"], unique=True)

    # send_logs
    op.create_table(
        "send_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id"), nullable=False),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("to_email", sa.String(300), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("body_snippet", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), server_default="queued"),
        sa.Column("provider", sa.String(30), nullable=True),
        sa.Column("provider_message_id", sa.String(200), nullable=True),
        sa.Column("sent_at", sa.DateTime, nullable=True),
        sa.Column("delivered_at", sa.DateTime, nullable=True),
        sa.Column("opened_at", sa.DateTime, nullable=True),
        sa.Column("clicked_at", sa.DateTime, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("response_webhook_payload", postgresql.JSON, nullable=True),
        sa.Column("retry_count", sa.Integer, server_default="0"),
    )
    op.create_index("ix_send_logs_job_id", "send_logs", ["job_id"])
    op.create_index("ix_send_logs_status", "send_logs", ["status"])
    op.create_index("ix_send_logs_provider_message_id", "send_logs", ["provider_message_id"])

    # search_tasks
    op.create_table(
        "search_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("candidate_id", sa.String(36), sa.ForeignKey("candidates.id"), nullable=False),
        sa.Column("job_titles", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("locations", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("portals", postgresql.JSON, nullable=True, server_default="[]"),
        sa.Column("max_results_per_portal", sa.Integer, server_default="50"),
        sa.Column("celery_task_id", sa.String(200), nullable=True),
        sa.Column("status", sa.String(30), server_default="queued"),
        sa.Column("jobs_found", sa.Integer, server_default="0"),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_search_tasks_candidate_id", "search_tasks", ["candidate_id"])
    op.create_index("ix_search_tasks_status", "search_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("search_tasks")
    op.drop_table("send_logs")
    op.drop_table("embeddings")
    op.drop_table("jobs")
    op.drop_table("candidates")
