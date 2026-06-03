from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_FILES = (
    PROJECT_ROOT / "infra" / ".env",
    PROJECT_ROOT / ".env",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    environment: Literal["development", "production"] = "development"
    admin_api_key: str = "change-me-secret"
    secret_key: str = "jwt-secret-key"
    log_level: str = "INFO"

    # Local logging
    log_dir: str = "backend/logs"          # directory for log files (relative to project root)
    log_to_file: bool = True               # write structured JSON logs to files
    log_rotation_mb: int = 50             # rotate log file after N MB

    # Database — local Docker PostgreSQL by default.
    # For cloud (Neon): set DATABASE_URL to the Neon connection string and POSTGRES_LOCAL=false.
    # POSTGRES_LOCAL=false enables Neon-specific tuning (pool_recycle, JIT off, keep-alive pings).
    database_url: str = "postgresql+asyncpg://jobhunter:jobhunter@postgres:5432/jobhunter"
    postgres_local: bool = True

    # Redis — local Docker by default (result backend + API cache).
    # For cloud (Upstash): use rediss:// URL with TLS.
    redis_url: str = "redis://redis:6379"
    celery_result_backend: str = "redis://redis:6379"

    # RabbitMQ — local Docker by default (Celery task broker).
    # For cloud (CloudAMQP): set RABBITMQ_URL to amqps:// URL.
    # Falls back to Redis broker if RABBITMQ_URL is empty.
    rabbitmq_url: str = "amqp://jobhunter:jobhunter@rabbitmq:5672/"
    celery_broker_url: str = "redis://redis:6379"

    @property
    def effective_broker_url(self) -> str:
        """Return RabbitMQ URL when available, otherwise fall back to Redis broker."""
        return self.rabbitmq_url if self.rabbitmq_url else self.celery_broker_url

    # LLM — Groq (text generation) or Ollama (local)
    llm_provider: Literal["groq", "ollama"] = "groq"
    # Groq
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"   # or mixtral-8x7b-32768, gemma2-9b-it
    # Groq rate limiting — shared across all workers via Redis sliding window
    groq_rpm: int = 10          # requests per minute (free tier = 10 RPM for 70B model)
    groq_tpm: int = 12000       # tokens per minute (informational; not enforced yet)
    # Comma-separated key aliases for multi-key round-robin (e.g. "key1,key2").
    # When set, rate_limiter.get_least_used_key() picks the least-loaded key.
    # The actual API key per alias must be provided separately (e.g. GROQ_API_KEY_KEY1).
    groq_api_keys: str = ""     # leave empty to use the single GROQ_API_KEY
    # Ollama (used as embedding backend when groq is text provider)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    ollama_embedding_model: str = "nomic-embed-text"

    # Vector DB
    vector_db_provider: Literal["pgvector", "pinecone", "local"] = "local"
    pinecone_api_key: str = ""
    pinecone_env: str = "us-east-1-aws"
    pinecone_index: str = "job-embeddings"

    # Email — provider: brevo | mailtrap | smtp
    email_provider: Literal["mailtrap", "brevo", "smtp"] = "brevo"
    # Mailtrap (sandbox testing)
    mailtrap_api_key: str = ""
    mailtrap_from_email: str = "hello@example.com"
    mailtrap_from_name: str = "Job Application Bot"
    mailtrap_sandbox: bool = True
    mailtrap_inbox_id: int = 0
    # Brevo (production transactional email)
    brevo_api_key: str = ""
    brevo_from_email: str = ""
    brevo_from_name: str = "Job Application Bot"
    brevo_webhook_secret: str = ""
    # SMTP fallback
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_use_tls: bool = True

    # Cloudflare R2 (S3-compatible)
    # Endpoint: https://<account_id>.r2.cloudflarestorage.com
    s3_endpoint_url: str = "https://<account_id>.r2.cloudflarestorage.com"
    s3_bucket_name: str = "jobhunter-resumes"
    s3_access_key: str = ""    # R2 API token access key ID
    s3_secret_key: str = ""    # R2 API token secret
    s3_region: str = "auto"    # R2 uses "auto" as region

    # Scraper
    proxy_url: str = ""
    respect_robots_txt: bool = True
    default_crawl_delay_seconds: float = 2.0
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""

    # Date freshness filter — jobs with posted_date older than this are skipped
    # during scraping. Default 30 days ("latest jobs only"); admin overrides are
    # clamped to max_job_age_days_hard_cap (90 days = 3 months).
    max_job_age_days: int = 30
    max_job_age_days_hard_cap: int = 90
    # When True, jobs with no parseable posted_date are also rejected.
    # Default True: undated listings are usually stale.
    scrape_strict_date_mode: bool = True

    # Role filter — when True, jobs whose title/description don't match the
    # PHP/Python keyword regex (see scraper/role_filter.py) are dropped during
    # scraping. Applies globally across all adapters.
    role_filter_enabled: bool = True

    # Email test override — when set, all outgoing emails are redirected to this
    # address regardless of the job's HR email. Leave empty for production sends.
    email_test_override: str = ""

    # Master switch — set to False to disable ALL automatic email sending.
    # When False: beat crons skip, workflow always requires approval, dispatch tasks no-op.
    # Manual sends via the API (dashboard "Send" button) are unaffected.
    auto_send_enabled: bool = False

    # ── LangChain / LangGraph AI settings ────────────────────────────────────
    # Master switch — set to False to disable all LangChain calls and revert to
    # the hardcoded template-based cover letter logic.
    langchain_enabled: bool = True
    # Minimum LangChain relevance score (0–100) to proceed with an application.
    # Jobs scoring below this threshold are discarded (status → "filtered").
    score_threshold: int = 60
    # Set to True to enable LangChain semantic PHP/Laravel detection as a 3rd
    # filter stage on top of keyword matching.  Off by default — keyword filter
    # is sufficient for most use cases.
    semantic_filter_enabled: bool = False

    # ── JWT auth ──────────────────────────────────────────────────────────────
    jwt_secret: str = "change-me-jwt-secret-32-chars-minimum"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    frontend_url: str = "http://localhost:3000"

    # ── Razorpay billing ──────────────────────────────────────────────────────
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # ── Worker tuning (managed by infra/worker.config.yml) ───────────────────
    # These are written to infra/.env by apply_worker_config.py.
    # Defaults match the hardcoded values previously in celery_app.py.
    worker_prefetch_multiplier: int = 1  # Reduced from 4 — prevents workers from grabbing tasks they can't process yet
    broker_pool_limit: int = 3
    task_soft_time_limit: int = 600
    task_time_limit: int = 720

    # Beat schedule intervals in seconds (crontab-based tasks don't use these)
    beat_scrape_interval: int = 7200        # 2 hours
    beat_refresh_covers_interval: int = 14400   # 4 hours
    beat_retry_sends_interval: int = 1800   # 30 min
    beat_cleanup_interval: int = 604800     # 7 days
    beat_fix_placeholder_interval: int = 1800   # 30 min
    beat_dispatch_ready_interval: int = 300     # 5 min (disabled; auto-send off)
    beat_auto_approve_interval: int = 600       # 10 min (disabled; auto-send off)
    beat_cover_status_interval: int = 3600      # 1 hour

    # ── Langfuse LLM observability ────────────────────────────────────────────
    # Get keys at https://cloud.langfuse.com → Settings → API Keys
    # Set LANGFUSE_ENABLED=true in .env to activate tracing.
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    # Accepts LANGFUSE_HOST or LANGFUSE_BASE_URL (both are common in docs/SDKs)
    langfuse_host: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_host", "LANGFUSE_HOST", "LANGFUSE_BASE_URL"),
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
