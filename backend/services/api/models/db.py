import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSON

from services.api.core.database import Base


def _uuid():
    return str(uuid.uuid4())


SENTINEL_TENANT_ID = "00000000-0000-0000-0000-000000000001"


# ─────────────────────────────────────────────────────────────────────────────
# SaaS / Multi-tenancy models
# ─────────────────────────────────────────────────────────────────────────────

class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    plan = Column(String(30), default="free")   # free | pro | premium
    status = Column(String(30), default="active")
    requires_approval = Column(Boolean, default=False)  # human-in-the-loop toggle
    auto_send = Column(Boolean, default=False)
    score_threshold = Column(Integer, default=60)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_tenants_slug", "slug"),)


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    email = Column(String(200), nullable=False)
    hashed_password = Column(String(200), nullable=False)
    is_verified = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    role = Column(String(20), default="member")  # owner | admin | member
    verification_token = Column(String(200), nullable=True)
    reset_token = Column(String(200), nullable=True)
    reset_token_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_users_email_tenant"),
        Index("ix_users_email", "email"),
        Index("ix_users_tenant_id", "tenant_id"),
    )


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    role = Column(String(20), default="member")
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),
        Index("ix_memberships_user_id", "user_id"),
        Index("ix_memberships_tenant_id", "tenant_id"),
    )


class BillingSubscription(Base):
    __tablename__ = "billing_subscriptions"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    plan = Column(String(30), nullable=False)
    status = Column(String(30), nullable=False)  # active | past_due | cancelled | trialing
    provider = Column(String(30), default="razorpay")
    provider_sub_id = Column(String(200), nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_billing_subscriptions_tenant_id", "tenant_id"),
    )


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    action_type = Column(String(50), nullable=True)  # send_application | generate_cover | score_job
    log_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_usage_logs_tenant_id", "tenant_id"),
        Index("ix_usage_logs_created_at", "created_at"),
        Index("ix_usage_logs_tenant_created_at", "tenant_id", "created_at"),
        Index("ix_usage_logs_action_type", "action_type"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    type = Column(String(50), nullable=True)  # job_match | application_sent | usage_warning
    message = Column(Text, nullable=True)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_tenant_id", "tenant_id"),
        Index("ix_notifications_user_read", "user_id", "is_read"),
        Index("ix_notifications_created_at", "created_at"),
    )


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    name = Column(String(200), nullable=False)
    email = Column(String(200), nullable=False)
    skills = Column(JSON, default=list)
    years_experience = Column(Integer, nullable=True)
    resume_url = Column(String(500), nullable=True)
    target_roles = Column(JSON, default=list)
    target_locations = Column(JSON, default=list)
    bio = Column(Text, nullable=True)
    cover_letter_template = Column(Text, nullable=True)
    static_cover_letter = Column(Text, nullable=True)
    linkedin_url = Column(String(300), nullable=True)
    github_url = Column(String(300), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_candidates_email_tenant"),
        Index("ix_candidates_tenant_id", "tenant_id"),
        Index("ix_candidates_email", "email"),
        Index("ix_candidates_is_active", "is_active"),
        Index("ix_candidates_tenant_active", "tenant_id", "is_active"),
    )


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=True)
    job_title = Column(String(300), nullable=False)
    company = Column(String(300), nullable=False)
    location = Column(String(300), nullable=True)
    job_description = Column(Text, nullable=True)
    job_url = Column(String(1000), nullable=False)
    posted_date = Column(DateTime, nullable=True)
    scraped_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    hr_email = Column(String(300), nullable=True)
    company_website = Column(String(500), nullable=True)
    recruiter_name = Column(String(200), nullable=True)
    source_portal = Column(String(50), nullable=False)
    status = Column(String(30), default="new")
    dedupe_hash = Column(String(64), nullable=False)
    salary_min = Column(Float, nullable=True)
    salary_max = Column(Float, nullable=True)
    salary_currency = Column(String(10), nullable=True)
    job_type = Column(String(50), nullable=True)
    experience_required = Column(String(100), nullable=True)
    raw_data = Column(JSON, nullable=True)
    relevance_score = Column(Float, nullable=True)
    score_breakdown = Column(JSON, nullable=True)  # LangChain scoring details
    cover_letter = Column(Text, nullable=True)
    cover_letter_generated_at = Column(DateTime, nullable=True)
    is_php_python = Column(Boolean, default=True, nullable=False, server_default="true")

    # HR email discovery tracking — prevents infinite retry loops
    hr_email_discovery_status = Column(
        String(30), nullable=True, default="pending",
        # pending | found | not_found | unreachable
    )
    hr_email_discovery_attempts = Column(Integer, nullable=True, default=0)
    hr_email_discovered_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "dedupe_hash", name="uq_jobs_tenant_dedupe"),
        # Single-column
        Index("ix_jobs_tenant_id", "tenant_id"),
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_candidate_id", "candidate_id"),
        Index("ix_jobs_dedupe_hash", "dedupe_hash"),
        Index("ix_jobs_source_portal", "source_portal"),
        Index("ix_jobs_scraped_at", "scraped_at"),
        Index("ix_jobs_posted_date", "posted_date"),
        Index("ix_jobs_updated_at", "updated_at"),
        Index("ix_jobs_relevance_score", "relevance_score"),
        Index("ix_jobs_hr_discovery_status", "hr_email_discovery_status"),
        Index("ix_jobs_hr_discovery_attempts", "hr_email_discovery_attempts"),
        Index("ix_jobs_cover_letter_generated_at", "cover_letter_generated_at"),
        Index("ix_jobs_company", "company"),
        # Composite
        Index("ix_jobs_status_scraped_at", "status", "scraped_at"),
        Index("ix_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_jobs_tenant_candidate", "tenant_id", "candidate_id"),
        Index("ix_jobs_status_candidate", "status", "candidate_id"),
        # Partial — cover_ready HR fetch
        Index(
            "ix_jobs_hr_discovery_cover_ready",
            "hr_email_discovery_attempts", "scraped_at",
            postgresql_where="hr_email IS NULL AND status = 'cover_generated'",
        ),
        # Partial — general backfill (WHERE hr_email IS NULL, status not terminal)
        Index(
            "ix_jobs_backfill_pending",
            "hr_email_discovery_attempts", "scraped_at",
            postgresql_where="hr_email IS NULL AND status NOT IN ('sent','bounced','error')",
        ),
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)
    vector_id = Column(String(200), nullable=True)
    embedding_source = Column(String(50), nullable=True)
    embedding_model = Column(String(100), nullable=True)
    embedding_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_embeddings_job_id", "job_id"),
        Index("ix_embeddings_tenant_id", "tenant_id"),
    )


class SendLog(Base):
    __tablename__ = "send_logs"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    job_id = Column(String(36), ForeignKey("jobs.id"), nullable=False)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=False)
    to_email = Column(String(300), nullable=False)
    subject = Column(String(500), nullable=True)
    body_snippet = Column(String(500), nullable=True)
    status = Column(String(30), default="queued")
    provider = Column(String(30), nullable=True)
    provider_message_id = Column(String(200), nullable=True)
    sent_at = Column(DateTime, nullable=True)
    delivered_at = Column(DateTime, nullable=True)
    opened_at = Column(DateTime, nullable=True)
    clicked_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    response_webhook_payload = Column(JSON, nullable=True)
    retry_count = Column(Integer, default=0)

    __table_args__ = (
        # Single-column
        Index("ix_send_logs_tenant_id", "tenant_id"),
        Index("ix_send_logs_job_id", "job_id"),
        Index("ix_send_logs_candidate_id", "candidate_id"),
        Index("ix_send_logs_status", "status"),
        Index("ix_send_logs_provider_message_id", "provider_message_id"),
        Index("ix_send_logs_sent_at", "sent_at"),
        # Composite
        Index("ix_send_logs_job_candidate_status", "job_id", "candidate_id", "status"),
        Index("ix_send_logs_tenant_sent_at", "tenant_id", "sent_at"),
        # Partial — retry task scan
        Index(
            "ix_send_logs_retry_pending",
            "sent_at",
            postgresql_where="status IN ('soft_bounce', 'queued')",
        ),
    )


class DirectSendLog(Base):
    __tablename__ = "direct_send_logs"

    id           = Column(String(36), primary_key=True, default=_uuid)
    tenant_id    = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                          default=lambda: SENTINEL_TENANT_ID)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=False)
    hr_email     = Column(String(300), nullable=False)
    sent_at      = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "candidate_id", "hr_email",
                         name="uq_direct_send_tenant_candidate_email"),
        Index("ix_direct_send_logs_tenant_candidate", "tenant_id", "candidate_id"),
    )


class BlacklistedCompany(Base):
    __tablename__ = "blacklisted_companies"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    name = Column(String(300), nullable=False)
    reason = Column(String(500), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_blacklist_tenant_name"),
        Index("ix_blacklisted_companies_tenant_id", "tenant_id"),
        Index("ix_blacklisted_companies_name", "name"),
    )


class SearchTask(Base):
    __tablename__ = "search_tasks"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False,
                       default=lambda: SENTINEL_TENANT_ID)
    candidate_id = Column(String(36), ForeignKey("candidates.id"), nullable=False)
    job_titles = Column(JSON, default=list)
    locations = Column(JSON, default=list)
    portals = Column(JSON, default=list)
    max_results_per_portal = Column(Integer, default=50)
    celery_task_id = Column(String(200), nullable=True)
    status = Column(String(30), default="queued")
    jobs_found = Column(Integer, default=0)
    jobs_old_skipped = Column(Integer, default=0)
    jobs_date_unavailable = Column(Integer, default=0)
    tasks_total = Column(Integer, default=0)
    tasks_completed = Column(Integer, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_search_tasks_tenant_id", "tenant_id"),
        Index("ix_search_tasks_candidate_id", "candidate_id"),
        Index("ix_search_tasks_status", "status"),
        Index("ix_search_tasks_created_at", "created_at"),
        Index("ix_search_tasks_status_created_at", "status", "created_at"),
    )


class CronRun(Base):
    """Persists the history of every cron / beat task execution.

    Populated by the @cron_monitored decorator in services/common/cron_monitor.py.
    The admin Cron Monitor page reads this table for run history, step timelines,
    durations, and pre/post state deltas.
    """

    __tablename__ = "cron_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    task_name = Column(String(200), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    celery_task_id = Column(String(200), nullable=True)
    # running | success | failure | timeout | skipped
    status = Column(String(20), default="running", nullable=False)
    error_summary = Column(String(500), nullable=True)
    error_traceback = Column(Text, nullable=True)
    # Snapshot of key DB counts captured before the task ran
    pre_state = Column(JSON, nullable=True)
    # Return value / counts after the task completed
    post_state = Column(JSON, nullable=True)
    # List of {"label": str, "started_at": iso, "ended_at": iso, "ok": bool}
    steps = Column(JSON, default=list)
    # beat | manual | chain
    triggered_by = Column(String(20), default="beat", nullable=False)
    worker_host = Column(String(200), nullable=True)

    __table_args__ = (
        Index("ix_cron_runs_task_started", "task_name", "started_at"),
        Index("ix_cron_runs_status_started", "status", "started_at"),
    )
