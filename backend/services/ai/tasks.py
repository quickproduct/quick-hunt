"""AI Celery tasks — embedding generation, cover letter generation, job ranking."""
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

SCORE_THRESHOLD = int(os.getenv("SCORE_THRESHOLD", "60"))

import structlog

from services.scraper.celery_app import celery_app
from services.common.async_utils import run_async as _run_async
from services.common.logging import log_exception
from services.common.cron_validators import cron_safe
from services.common.cron_monitor import cron_monitored

logger = structlog.get_logger(__name__)

# ─── Cover letter templates (per candidate) ──────────────────────────────────
# Fixed templates — LLM only fills [Job Title] and [Company Name] placeholders.
# If company is "Unknown", LLM extracts the real name from the job description.
# Key: lowercase candidate name. Falls back to "default" if no match.

COVER_LETTER_TEMPLATES: dict[str, str] = {
    "suraj shetty": """Dear Team,

I am excited to apply for the [Job Title] role at [Company Name]. I am a backend software engineer with experience in Laravel, Python/FastAPI, React, MySQL, MongoDB, Redis, RabbitMQ, Kafka, Docker, Kubernetes, and AWS, and I have worked on scalable systems in healthcare, payments, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, performance optimization, queue-based processing, and microservices architecture. I have also built AI-powered projects using LangChain, LangGraph, ChromaDB, and GroqAI, which strengthened my ability to work on modern, production-oriented applications.

I would be glad to bring my experience and problem-solving approach to [Company Name]. Thank you for your time and consideration.""",

    "gunjan pandey": """Dear Team,

I am excited to apply for the [Job Title] role at [Company Name]. I am a backend software engineer with experience in PHP, Python, Laravel, FastAPI, ReactJS, MySQL, MongoDB, Redis, RabbitMQ, Docker, Kubernetes, and AWS, and I have worked on scalable systems in crowdfunding, travel booking, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, payment gateway integrations, performance optimization, and microservices architecture. I have also worked on security improvements and built AI-powered projects using LangChain, LangGraph, ChromaDB, and GroqAI, strengthening my ability to develop modern, production-ready applications.

I would be glad to bring my experience and problem-solving approach to [Company Name]. Thank you for your time and consideration.""",
}

# Non-PHP/Python cover letter templates — used for Java, Node.js, and other backend roles.
# PHP and Laravel are intentionally omitted so the letter reads naturally for those stacks.
NON_PHP_COVER_LETTER_TEMPLATES: dict[str, str] = {
    "suraj shetty": """Dear Team,

I am excited to apply for the [Job Title] role at [Company Name]. I am a backend software engineer with experience in Python/FastAPI, React, MySQL, MongoDB, Redis, RabbitMQ, Kafka, Docker, Kubernetes, and AWS, and I have worked on scalable systems in healthcare, payments, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, performance optimization, queue-based processing, and microservices architecture. I have also built AI-powered projects using LangChain, LangGraph, ChromaDB, and GroqAI, which strengthened my ability to work on modern, production-oriented applications.

I would be glad to bring my experience and problem-solving approach to [Company Name]. Thank you for your time and consideration.""",

    "gunjan pandey": """Dear Hiring Manager,

I am Gunjan Pandey, an Immediate Joiner with 5 years of experience, and I am excited to apply for the [Job Title] role. I am a Backend Software Engineer with experience in PHP, Python, Laravel, FastAPI, ReactJS, MySQL, MongoDB, Redis, RabbitMQ, Docker, Kubernetes, and AWS, and I have worked on scalable systems in crowdfunding, travel booking, logistics, and SaaS.

In my recent roles, I have handled backend development, API integrations, payment gateway integrations, performance optimization, and microservices architecture. I have also worked on security improvements and built AI-powered applications using LangChain, LangGraph, ChromaDB, and GroqAI, strengthening my ability to develop modern, production-ready applications.

I would be glad to bring my experience and problem-solving approach to your team. Thank you for your time and consideration.

You can reach me at:
Phone: +91 72087 05524
Email: gunjanap2018@gmail.com

Sincerely,
Gunjan Pandey""",
}

EXTRACT_COMPANY_SYSTEM = (
    "Extract the hiring company name from the job info provided. "
    "Respond with ONLY the company name — no punctuation, no explanation. "
    "If you cannot determine it, respond with exactly: your organization"
)


async def _fill_cover_letter(job, candidate, callbacks=None) -> str:
    """Generate a cover letter for a job + candidate.

    For non-PHP/Python jobs: uses the hardcoded static template directly
    (no LLM call). These are backend/engineering roles that often have
    real HR email addresses, making them worth applying to with a generic
    but professional cover letter.

    For PHP/Python jobs, priority:
    1. Candidate's custom cover_letter_template — if set, replaces {job-title}
       and {company-name} and is used as-is (no AI call).
    2. LangChain (generate_cover_letter_langchain) — richer, personalised output.
    3. Hardcoded template fallback — used when LangChain is disabled or fails.

    LangChain calls (priority 2) are gated by a Redis sliding-window rate limiter
    so that concurrent workers never exceed GROQ_RPM requests per minute globally.
    """
    # ── Non-PHP/Python path: use candidate's own static cover, no LLM ─────────
    # Also catches jobs the scraper misclassified — trust the LLM scorer's verdict.
    _breakdown = getattr(job, "score_breakdown", None) or {}
    _llm_non_php = _breakdown.get("is_php_laravel") is False
    if not getattr(job, "is_php_python", True) or _llm_non_php:
        static = getattr(candidate, "static_cover_letter", None)
        if static and static.strip():
            return static
        tmpl = getattr(candidate, "cover_letter_template", None)
        if tmpl and tmpl.strip():
            return (
                tmpl
                .replace("{job-title}", job.job_title or "")
                .replace("{company-name}", job.company or "")
            )
        return await _fill_cover_letter_template(job, candidate)

    # ── Priority 1: candidate's own template — no LLM call ───────────────────
    template = getattr(candidate, "cover_letter_template", None)
    if template and template.strip():
        return (
            template
            .replace("{job-title}", job.job_title or "")
            .replace("{company-name}", job.company or "")
        )

    from services.api.core.config import get_settings
    settings = get_settings()

    candidate_key = (candidate.name or "").lower()
    has_hardcoded = candidate_key in COVER_LETTER_TEMPLATES

    if getattr(settings, "langchain_enabled", True) and not has_hardcoded:
        # Acquire a global Groq rate-limit slot before hitting the API.
        # wait_for_groq_slot sleeps (with jitter) until a slot is free so
        # concurrent asyncio coroutines naturally spread out to ≤ GROQ_RPM/min.
        from services.ai.rate_limiter import get_least_used_key, wait_for_groq_slot
        key_id = await get_least_used_key()
        slot_ok = await wait_for_groq_slot(key_id)
        if not slot_ok:
            logger.warning("cover_rate_limit_timeout", job_id=job.id)
            # Fall through to hardcoded template rather than dropping the job
        else:
            try:
                from services.ai.cover_letter import generate_cover_letter_langchain
                result = await generate_cover_letter_langchain(
                    job_title=job.job_title,
                    company=job.company or "",
                    job_description=job.job_description or "",
                    candidate_name=candidate.name,
                    candidate_skills=candidate.skills or [],
                    candidate_bio=candidate.bio or "",
                    callbacks=callbacks,
                )
                return result.full_text
            except Exception as exc:
                logger.warning("langchain_cover_fallback", job_id=job.id, error=str(exc))

    # ── Hardcoded template fallback ───────────────────────────────────────────
    return await _fill_cover_letter_template(job, candidate)


async def _fill_cover_letter_template(job, candidate) -> str:
    """Fill the candidate-specific hardcoded template.

    Uses NON_PHP_COVER_LETTER_TEMPLATES for non-PHP/Python jobs to avoid
    mentioning PHP/Laravel in cover letters sent to Java or Node.js roles.
    """
    from services.ai.llm_adapter import get_llm_adapter

    candidate_key = (candidate.name or "").lower()
    # Treat as non-PHP if scraper flag says so OR if the LLM scorer explicitly
    # identified it as non-PHP (catches jobs misclassified by the scraper).
    breakdown = getattr(job, "score_breakdown", None) or {}
    llm_says_non_php = breakdown.get("is_php_laravel") is False
    is_non_php = not getattr(job, "is_php_python", True) or llm_says_non_php
    template_dict = NON_PHP_COVER_LETTER_TEMPLATES if is_non_php else COVER_LETTER_TEMPLATES
    template = template_dict.get(
        candidate_key,
        template_dict.get("default", list(template_dict.values())[0]),
    )

    company = (job.company or "").strip()
    if not company or company.lower() == "unknown":
        snippet = (job.job_description or "")[:600]
        try:
            llm = get_llm_adapter()
            extracted = await llm.generate_text(
                prompt=f"Job title: {job.job_title}\nDescription snippet: {snippet}",
                system_prompt=EXTRACT_COMPANY_SYSTEM,
                max_tokens=20,
            )
            company = extracted.strip() or "your organization"
        except Exception:
            company = "your organization"

    return (
        template
        .replace("[Job Title]", job.job_title)
        .replace("[Company Name]", company)
    )


async def _get_job_and_candidate(job_id: str, candidate_id: str) -> tuple[Optional[object], Optional[object]]:
    from sqlalchemy import select

    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Candidate, Job

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        job_result = await session.get(Job, job_id)
        candidate_result = await session.get(Candidate, candidate_id) if candidate_id else None
    return job_result, candidate_result


@celery_app.task(
    name="services.ai.tasks.generate_embedding_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def generate_embedding_task(self, job_id: str) -> dict:
    """Generate and store embedding for a job's description."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )
    logger.info("embedding_task_started", job_id=job_id)

    async def _run():
        from sqlalchemy import select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Embedding, Job
        from services.ai.llm_adapter import get_embedding_adapter
        from services.ai.vector_adapter import get_vector_adapter
        from services.api.core.config import get_settings

        settings = get_settings()
        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            try:
                job = await session.get(Job, job_id)
                if not job:
                    logger.warning("job_not_found", job_id=job_id)
                    return {"status": "skipped", "reason": "job not found"}

                text = f"{job.job_title} at {job.company}\n{job.job_description or ''}"
                emb_adapter = get_embedding_adapter()
                vector = await emb_adapter.generate_embedding(text)
                if not vector:
                    logger.warning("embedding_empty_skipping", job_id=job_id)
                    return {"status": "skipped", "reason": "embedding provider unavailable"}

                emb_id = str(uuid.uuid4())
                metadata = {
                    "job_id": job_id,
                    "source": settings.llm_provider,
                    "model": settings.openai_embedding_model if settings.llm_provider == "openai" else settings.ollama_embedding_model,
                }
                vector_store = get_vector_adapter()
                await vector_store.upsert(emb_id, vector, metadata)

                # Also persist in embeddings table
                existing = await session.execute(
                    select(Embedding).where(Embedding.job_id == job_id)
                )
                existing_emb = existing.scalar_one_or_none()
                if existing_emb:
                    existing_emb.embedding_json = vector
                    existing_emb.embedding_source = metadata["source"]
                    existing_emb.embedding_model = metadata["model"]
                    existing_emb.vector_id = emb_id
                else:
                    session.add(Embedding(
                        id=emb_id,
                        job_id=job_id,
                        vector_id=emb_id,
                        embedding_source=metadata["source"],
                        embedding_model=metadata["model"],
                        embedding_json=vector,
                    ))
                await session.commit()
            except Exception as commit_exc:
                try:
                    await session.rollback()
                except Exception as rollback_exc:
                    logger.warning(
                        "rollback_failed",
                        job_id=job_id,
                        error=str(rollback_exc)[:200],
                    )

                from sqlalchemy.exc import IntegrityError
                if isinstance(commit_exc, IntegrityError):
                    exc_str = str(commit_exc)
                    if "ForeignKeyViolationError" in exc_str or "foreign key constraint" in exc_str:
                        logger.warning(
                            "embedding_skipped_job_deleted",
                            job_id=job_id,
                            error=exc_str[:200],
                        )
                        return {"status": "skipped", "reason": "job deleted before embedding insert"}

                raise

        logger.info("embedding_task_complete", job_id=job_id, emb_id=emb_id)
        return {"status": "ok", "embedding_id": emb_id}

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "embedding_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.generate_cover_letter_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def generate_cover_letter_task(
    self,
    job_id: str,
    candidate_id: str,
    tone: str = "professional",
    custom_instructions: str = "",
) -> dict:
    """Fill the cover letter template for a job + candidate."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )
    logger.info("cover_letter_task_started", job_id=job_id, candidate_id=candidate_id)

    async def _run():
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job
        from services.ai.observability import get_callback_handler, flush

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            candidate = await session.get(Candidate, candidate_id)

            if not job:
                return {"status": "skipped", "reason": "job not found"}
            if not candidate:
                return {"status": "skipped", "reason": "candidate not found"}

            # Create a Langfuse trace for this cover-letter task so all LLM
            # sub-calls (LangChain + direct Groq) are grouped under one trace.
            handler = get_callback_handler(
                "cover_letter_task",
                session_id=job_id,
                tags=["cover_letter", "celery"],
                metadata={
                    "job_id": job_id,
                    "candidate_id": candidate_id,
                    "job_title": job.job_title,
                    "company": job.company,
                },
            )
            callbacks = [handler] if handler else None

            cover_letter = await _fill_cover_letter(job, candidate, callbacks=callbacks)

            job.cover_letter = cover_letter
            job.cover_letter_generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
            if job.status in ("new", "filtered", "scoring"):
                job.status = "cover_generated"
            await session.commit()

        logger.info("cover_letter_task_complete", job_id=job_id)
        flush()
        return {"status": "ok", "job_id": job_id}

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "cover_letter_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.score_job_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def score_job_task(self, job_id: str, candidate_id: str) -> dict:
    """Score a single job for relevance immediately after scraping.

    For PHP/Python jobs: runs LLM scoring via Groq.
    For non-PHP/Python jobs: skips LLM, assigns default score — these get
    a static cover letter instead of an LLM-generated one.

    Irrelevant PHP/Python jobs (score < threshold or wrong stack) are marked
    'filtered' so cover-letter crons skip them. Relevant jobs stay 'new' and
    are picked up by fill_missing_covers_task within minutes.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        job_id=job_id,
    )
    logger.info("score_job_task_started", job_id=job_id)

    async def _run():
        from sqlalchemy import select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            if not job:
                return {"status": "skipped", "reason": "job not found"}

            # Non-PHP/Python jobs: skip LLM scoring entirely, assign default score
            if not getattr(job, "is_php_python", True):
                job.relevance_score = 50.0
                job.score_breakdown = {
                    "overall_score": 50,
                    "skills_match": 40,
                    "experience_match": 60,
                    "location_match": 50,
                    "role_alignment": 40,
                    "is_php_laravel": False,
                    "detected_role_type": "non_php_python",
                    "reasoning": "Non-PHP/Python backend role — static cover letter path",
                }
                logger.info(
                    "score_job_task_skipped_non_php_python",
                    job_id=job_id,
                    job_title=job.job_title,
                )
                try:
                    await session.commit()
                except Exception as _commit_exc:
                    from sqlalchemy.orm.exc import StaleDataError
                    if isinstance(_commit_exc, StaleDataError):
                        logger.warning("score_job_stale_skip", job_id=job_id)
                        return {"status": "skipped", "reason": "concurrent update"}
                    raise
                return {"status": "ok", "job_id": job_id, "score": 50, "path": "static_cover"}

            candidate = await session.get(Candidate, candidate_id) if candidate_id else None
            if not candidate:
                fallback = await session.execute(
                    select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
                )
                candidate = fallback.scalar_one_or_none()
                if not candidate:
                    return {"status": "skipped", "reason": "no candidate"}

            from services.ai.scoring import score_job_relevance

            score = await score_job_relevance(
                job_title=job.job_title or "",
                job_description=job.job_description or "",
                company=job.company or "",
                candidate_skills=candidate.skills or [],
                candidate_experience=candidate.years_experience or 0,
                candidate_bio=candidate.bio or "",
            )

            job.relevance_score = float(score.overall_score)
            job.score_breakdown = score.model_dump()

            if not score.is_php_laravel or score.overall_score < SCORE_THRESHOLD:
                job.status = "filtered"
                logger.info(
                    "score_job_task_discarded",
                    job_id=job_id,
                    score=score.overall_score,
                    is_php=score.is_php_laravel,
                )
            else:
                logger.info(
                    "score_job_task_passed",
                    job_id=job_id,
                    score=score.overall_score,
                )

            await session.commit()

        return {"status": "ok", "job_id": job_id, "score": score.overall_score}

    try:
        return _run_async(_run())
    except Exception as exc:
        from sqlalchemy.orm.exc import StaleDataError
        from sqlalchemy.exc import InterfaceError
        if isinstance(exc, (StaleDataError, InterfaceError)):
            logger.warning(
                "score_job_task_connection_skip",
                job_id=job_id,
                error_type=type(exc).__name__,
            )
            return {"status": "skipped", "reason": "transient db error"}
        log_exception(logger, "score_job_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.refresh_cover_letters_task",
)
@cron_safe(
    task_name="refresh_cover_letters_task",
    singleton_ttl_seconds=300,  # 5 min - allows rapid re-runs
    max_queue_depth=3000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=7200,
)
@cron_monitored("refresh_cover_letters_task")
def refresh_cover_letters_task() -> dict:
    """
    Cron task — runs every 4 hours to:
    1. Regenerate existing cover letters using the new template (overwrite old LLM output).
    2. Generate first-time covers for jobs that have an HR email but no cover yet.

    Processes up to 100 jobs per run. NULL cover_letter_generated_at (never generated)
    is prioritised; then oldest-generated jobs are refreshed next.
    ALL jobs are processed regardless of status.
    """
    BATCH_SIZE = 100
    SKIP_STATUSES = ["sent", "bounced", "error"]
    logger.info("refresh_cover_letters_task_started")

    async def _run():
        import asyncio as _asyncio

        from sqlalchemy import select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            # Fallback candidate — used when job.candidate_id is NULL
            fallback_result = await session.execute(
                select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
            )
            fallback_candidate = fallback_result.scalar_one_or_none()
            if not fallback_candidate:
                logger.warning("refresh_skipped_no_candidate")
                return {"status": "skipped", "reason": "no active candidate"}

            q = (
                select(Job)
                .where(~Job.status.in_(SKIP_STATUSES))
                .order_by(Job.cover_letter_generated_at.asc().nullsfirst())
                .limit(BATCH_SIZE)
                # SKIP LOCKED: concurrent workers take different rows, preventing
                # StaleDataError when two instances UPDATE the same job row.
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(q)
            jobs = result.scalars().all()

            # Pre-fetch all unique candidates in one query — avoids N concurrent
            # DB sessions during the parallel LLM phase (would exhaust the pool).
            candidate_ids = list({j.candidate_id for j in jobs if j.candidate_id})
            candidates: dict = {}
            if candidate_ids:
                from sqlalchemy import select as _sel
                cand_result = await session.execute(
                    _sel(Candidate).where(Candidate.id.in_(candidate_ids))
                )
                for c in cand_result.scalars().all():
                    candidates[c.id] = c

            job_data = [(j.id, j.candidate_id, j.job_title, j.company,
                          j.job_description, j.job_url, j.source_portal) for j in jobs]

        async def _process_one(job_id, candidate_id, job_title, company,
                               job_description, job_url, source_portal) -> tuple[str, str | None]:
            candidate = candidates.get(candidate_id) if candidate_id else None
            if not candidate:
                candidate = fallback_candidate
            try:
                from services.api.core.database import get_worker_session_factory as _wsf
                from services.api.models.db import Job as _Job
                _sf = _wsf()
                async with _sf() as _s:
                    job = await _s.get(_Job, job_id)
                    if not job:
                        return job_id, None
                    cover = await _fill_cover_letter(job, candidate)
                    return job_id, cover
            except Exception as e:
                log_exception(logger, "refresh_single_job_failed", e, job_id=job_id)
                return job_id, None

        results = await _asyncio.gather(*[_process_one(*jd) for jd in job_data])

        # Bulk UPDATE
        from sqlalchemy import bindparam, update as sa_update

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        success_pairs = [(jid, c) for jid, c in results if c]
        skipped = len(results) - len(success_pairs)
        refreshed = 0

        if success_pairs:
            async with session_factory() as session:
                try:
                    await session.execute(
                        sa_update(Job.__table__)
                        .where(Job.__table__.c.id == bindparam("_id"))
                        .values(
                            cover_letter=bindparam("_cover"),
                            cover_letter_generated_at=bindparam("_ts"),
                        ),
                        [{"_id": jid, "_cover": c, "_ts": now} for jid, c in success_pairs],
                    )
                    await session.execute(
                        sa_update(Job.__table__)
                        .where(Job.__table__.c.id.in_([jid for jid, _ in success_pairs]))
                        .where(Job.__table__.c.status.in_(["new", "filtered", "scoring"]))
                        .values(status="cover_generated"),
                    )
                    await session.commit()
                    refreshed = len(success_pairs)
                except Exception as commit_err:
                    await session.rollback()
                    log_exception(logger, "refresh_commit_failed", commit_err)

        logger.info(
            "refresh_cover_letters_task_complete",
            refreshed=refreshed,
            skipped=skipped,
        )
        return {"status": "ok", "refreshed": refreshed, "skipped": skipped}

    return _run_async(_run())


@celery_app.task(
    name="services.ai.tasks.refresh_non_php_covers_task",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
)
def refresh_non_php_covers_task(self) -> dict:
    """One-shot / on-demand task — re-assign static cover letters to all
    non-PHP/Python jobs that currently have a PHP-focused cover letter.

    Run this once after deploying the static cover letter fix to backfill
    existing jobs.  Safe to run multiple times (idempotent — only updates
    jobs where the cover letter would actually change).

    Skips jobs with terminal statuses (sent / bounced / error).
    """
    BATCH_SIZE = 200
    SKIP_STATUSES = ["sent", "bounced", "error"]
    logger.info("refresh_non_php_covers_task_started")

    async def _run():
        from sqlalchemy import select, false

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            fallback_result = await session.execute(
                select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
            )
            fallback_candidate = fallback_result.scalar_one_or_none()
            if not fallback_candidate:
                logger.warning("refresh_non_php_covers_skipped_no_candidate")
                return {"status": "skipped", "reason": "no active candidate"}

            q = (
                select(Job)
                .where(Job.is_php_python.is_(false()))
                .where(Job.cover_letter.isnot(None))
                .where(~Job.status.in_(SKIP_STATUSES))
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(q)
            jobs = result.scalars().all()

            candidate_ids = list({j.candidate_id for j in jobs if j.candidate_id})
            candidates: dict = {}
            if candidate_ids:
                from sqlalchemy import select as _sel
                cand_result = await session.execute(
                    _sel(Candidate).where(Candidate.id.in_(candidate_ids))
                )
                for c in cand_result.scalars().all():
                    candidates[c.id] = c

            job_data = [(j.id, j.candidate_id) for j in jobs]

        from sqlalchemy import update as _upd
        from services.api.models.db import Job as _Job

        updated = 0
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        async with session_factory() as session:
            for job_id, candidate_id in job_data:
                try:
                    job = await session.get(_Job, job_id)
                    if not job:
                        continue
                    candidate = candidates.get(candidate_id) or fallback_candidate
                    new_cover = await _fill_cover_letter(job, candidate)
                    if new_cover and new_cover != job.cover_letter:
                        await session.execute(
                            _upd(_Job)
                            .where(_Job.id == job_id)
                            .values(
                                cover_letter=new_cover,
                                cover_letter_generated_at=now,
                            )
                        )
                        updated += 1
                except Exception as exc:
                    log_exception(logger, "refresh_non_php_single_failed", exc, job_id=job_id)

            try:
                await session.commit()
            except Exception as commit_err:
                await session.rollback()
                log_exception(logger, "refresh_non_php_commit_failed", commit_err)

        logger.info("refresh_non_php_covers_task_complete", updated=updated, total=len(job_data))
        return {"status": "ok", "updated": updated, "total": len(job_data)}

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "refresh_non_php_covers_task_failed", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.fill_missing_covers_task",
)
@cron_safe(
    task_name="fill_missing_covers_task",
    singleton_ttl_seconds=300,  # 5 min - matches cron interval
    max_runs_per_hour=12,  # Every 5 min = 12/hour
    max_queue_depth=2000,  # Don't generate if queue is backed up
    circuit_failure_threshold=5,  # More lenient - AI can fail transiently
    circuit_recovery_seconds=1800,
)
@cron_monitored("fill_missing_covers_task")
def fill_missing_covers_task() -> dict:
    """
    Cron task — generates cover letters for jobs that have none yet.
    Two-tier priority: jobs with hr_email (send-ready) come first, then rest.
    Processes up to BATCH_SIZE jobs per run. Skips sent/bounced/error.
    """
    BATCH_SIZE = 50  # 50 covers × Groq 10 RPM = 5 min; fits within cron interval
    SKIP_STATUSES = ["sent", "bounced", "error"]
    logger.info("fill_missing_covers_task_started")

    async def _run():
        import asyncio as _asyncio

        from sqlalchemy import case, func, select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            fallback_result = await session.execute(
                select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
            )
            fallback_candidate = fallback_result.scalar_one_or_none()
            if not fallback_candidate:
                logger.warning("fill_covers_skipped_no_candidate")
                return {"status": "skipped", "reason": "no active candidate"}

            # Two-tier: jobs with hr_email (priority, current month) first,
            # then all other eligible jobs. This replaces priority_cover_for_emailed_jobs_task.
            result = await session.execute(
                select(Job)
                .where(Job.cover_letter.is_(None))
                .where(~Job.status.in_(SKIP_STATUSES))
                .order_by(
                    case(
                        (
                            Job.hr_email.isnot(None)
                            & (Job.posted_date >= func.date_trunc("month", func.current_date())),
                            0,
                        ),
                        (Job.hr_email.isnot(None), 1),
                        else_=2,
                    ),
                    Job.scraped_at.asc(),
                )
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            jobs = result.scalars().all()

            # Pre-fetch all unique candidates in one query — avoids opening
            # N concurrent DB sessions during the parallel LLM phase.
            candidate_ids = list({j.candidate_id for j in jobs if j.candidate_id})
            candidates: dict = {}
            if candidate_ids:
                from sqlalchemy import select as _sel
                cand_result = await session.execute(
                    _sel(Candidate).where(Candidate.id.in_(candidate_ids))
                )
                for c in cand_result.scalars().all():
                    candidates[c.id] = c

            job_data = [(j.id, j.candidate_id, j.job_title, j.company,
                          j.job_description, j.job_url, j.source_portal) for j in jobs]

        async def _process_one(job_id, candidate_id, job_title, company,
                               job_description, job_url, source_portal) -> tuple[str, str | None]:
            candidate = candidates.get(candidate_id) if candidate_id else None
            if not candidate:
                candidate = fallback_candidate
            try:
                from services.api.core.database import get_worker_session_factory as _wsf
                from services.api.models.db import Job as _Job
                _sf = _wsf()
                async with _sf() as _s:
                    job = await _s.get(_Job, job_id)
                    if not job:
                        return job_id, None
                    cover = await _fill_cover_letter(job, candidate)
                    return job_id, cover
            except Exception as e:
                log_exception(logger, "fill_cover_failed", e, job_id=job_id)
                return job_id, None

        results = await _asyncio.gather(*[_process_one(*jd) for jd in job_data])

        # Bulk UPDATE
        from sqlalchemy import bindparam, update as sa_update

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        success_pairs = [(jid, c) for jid, c in results if c]
        skipped = len(results) - len(success_pairs)
        filled = 0

        if success_pairs:
            async with session_factory() as session:
                try:
                    await session.execute(
                        sa_update(Job.__table__)
                        .where(Job.__table__.c.id == bindparam("_id"))
                        .values(
                            cover_letter=bindparam("_cover"),
                            cover_letter_generated_at=bindparam("_ts"),
                        ),
                        [{"_id": jid, "_cover": c, "_ts": now} for jid, c in success_pairs],
                    )
                    await session.execute(
                        sa_update(Job.__table__)
                        .where(Job.__table__.c.id.in_([jid for jid, _ in success_pairs]))
                        .where(Job.__table__.c.status.in_(["new", "filtered", "scoring"]))
                        .values(status="cover_generated"),
                    )
                    await session.commit()
                    filled = len(success_pairs)
                except Exception as commit_err:
                    await session.rollback()
                    log_exception(logger, "fill_covers_commit_failed", commit_err)

        logger.info("fill_missing_covers_task_complete", filled=filled, skipped=skipped)
        return {"status": "ok", "filled": filled, "skipped": skipped}

    return _run_async(_run())


@celery_app.task(
    name="services.ai.tasks.rank_jobs_task",
)
def rank_jobs_task(candidate_id: str) -> dict:
    """Rank all unscored jobs for a candidate using cosine similarity."""
    logger.info("rank_jobs_task_started", candidate_id=candidate_id)

    async def _run():
        from sqlalchemy import select, update

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job
        from services.ai.llm_adapter import get_embedding_adapter
        from services.ai.vector_adapter import get_vector_adapter

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            candidate = await session.get(Candidate, candidate_id)
            if not candidate:
                return {"status": "skipped"}

            # Build candidate profile text for embedding
            skills_str = ", ".join(candidate.skills or [])
            profile_text = f"{candidate.name} — skills: {skills_str}. Bio: {candidate.bio or ''}."

            emb_adapter = get_embedding_adapter()
            candidate_vector = await emb_adapter.generate_embedding(profile_text)
            if not candidate_vector:
                logger.warning("ranking_skipped_no_embedding", candidate_id=candidate_id)
                return {"status": "skipped", "reason": "embedding provider unavailable"}

            vector_store = get_vector_adapter()
            matches = await vector_store.query(candidate_vector, top_k=100)

            if matches:
                match_cases = []
                for match in matches:
                    match_cases.append({"id": match["job_id"], "score": match["score"]})

                from sqlalchemy import case as sa_case
                score_map = {m["id"]: m["score"] for m in match_cases}
                job_ids = list(score_map.keys())
                whens = {jid: score for jid, score in score_map.items()}
                await session.execute(
                    update(Job)
                    .where(Job.id.in_(job_ids), Job.candidate_id == candidate_id)
                    .values(relevance_score=sa_case(whens, value=Job.id))
                )
            await session.commit()
            updated = len(matches)

        logger.info("rank_jobs_task_complete", candidate_id=candidate_id, updated=updated)
        return {"status": "ok", "updated": updated}

    return _run_async(_run())


# ------------------------------------------------------------------ #
# LangGraph application workflow task                                  #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.ai.tasks.run_application_workflow_task",
    bind=True,
    max_retries=2,
)
def run_application_workflow_task(self, job_id: str, candidate_id: str) -> dict:
    """Run the full LangGraph application workflow for a single job + candidate.

    Flow: AnalyzeJob → ScoreJob → (score >= threshold) → GenerateCover →
          RequireApproval → SendApplication  OR  DiscardJob.

    Celery executes this as one synchronous task; LangGraph controls internal
    branching and stores checkpoints in Redis (TTL 24 h) for human-in-the-loop
    approval flows.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )
    logger.info("workflow_task_started", job_id=job_id, candidate_id=candidate_id)

    async def _run():
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job
        from services.ai.workflow import build_workflow

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            job = await session.get(Job, job_id)
            candidate = await session.get(Candidate, candidate_id)

        if not job:
            logger.warning("workflow_job_not_found", job_id=job_id)
            return {"status": "skipped", "reason": "job not found"}
        if not candidate:
            logger.warning("workflow_candidate_not_found", candidate_id=candidate_id)
            return {"status": "skipped", "reason": "candidate not found"}

        # Resolve tenant auto_send so the approval node respects it.
        # Without this, the workflow always stops at pending_approval regardless
        # of whether the tenant has opted into automatic sending.
        tenant_auto_send = False
        async with session_factory() as _ts:
            if hasattr(candidate, "tenant_id") and candidate.tenant_id:
                from services.api.models.db import Tenant
                _tenant = await _ts.get(Tenant, candidate.tenant_id)
                if _tenant:
                    tenant_auto_send = bool(_tenant.auto_send)
            elif hasattr(job, "tenant_id") and job.tenant_id:
                from services.api.models.db import Tenant
                _tenant = await _ts.get(Tenant, job.tenant_id)
                if _tenant:
                    tenant_auto_send = bool(_tenant.auto_send)

        initial_state = {
            "job_id": job_id,
            "candidate_id": candidate_id,
            "job_data": {
                "job_title": job.job_title,
                "company": job.company,
                "location": job.location,
                "job_description": job.job_description,
                "job_url": job.job_url,
                "source_portal": job.source_portal,
                "is_php_python": getattr(job, "is_php_python", True),
            },
            "candidate_data": {
                "name": candidate.name,
                "email": candidate.email,
                "skills": candidate.skills or [],
                "years_experience": candidate.years_experience or 0,
                "bio": candidate.bio or "",
                "auto_send": tenant_auto_send,
            },
            "job_analysis": None,
            "relevance_score": None,
            "cover_letter": None,
            "approval_status": "pending",
            "send_result": None,
            "error": None,
        }

        from services.ai.observability import get_callback_handler, flush

        # One Langfuse trace covers the entire workflow: analyze → score →
        # generate cover → (approve) → send.  Scoring and cover letter spans
        # are nested under this trace via callback propagation.
        handler = get_callback_handler(
            "application_workflow",
            session_id=job_id,
            tags=["workflow", "langgraph"],
            metadata={
                "job_id": job_id,
                "candidate_id": candidate_id,
                "job_title": job.job_title,
                "company": job.company,
                "source_portal": job.source_portal,
            },
        )

        # Checkpointing disabled: RedisSaver.from_conn_string hangs on Upstash TLS.
        # Approval state is tracked via job.status in DB — no LangGraph resume needed.
        workflow = build_workflow(use_checkpointing=False)
        config = {
            "configurable": {"thread_id": job_id},
            "callbacks": [handler] if handler else [],
        }
        result = await workflow.ainvoke(initial_state, config=config)
        flush()

        logger.info(
            "workflow_task_complete",
            job_id=job_id,
            approval_status=result.get("approval_status"),
            score=result.get("relevance_score", {}).get("overall_score") if result.get("relevance_score") else None,
        )
        return {
            "status": "ok",
            "job_id": job_id,
            "approval_status": result.get("approval_status"),
        }

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "workflow_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.check_cover_letter_status_task",
)
@cron_safe(
    task_name="check_cover_letter_status_task",
    singleton_ttl_seconds=300,  # 5 min lock
    max_runs_per_hour=2,  # Every 1 hour = 2/hour max with buffer
    max_queue_depth=3000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=3600,
)
@cron_monitored("check_cover_letter_status_task")
def check_cover_letter_status_task() -> dict:
    """
    Cron task — runs every hour to check cover letter freshness status.

    Reports:
    - Total jobs checked (excluding terminal statuses: sent, bounced, error)
    - Fresh covers: cover_letter_generated_at >= candidate.updated_at
    - Stale covers: cover_letter_generated_at < candidate.updated_at
    - Missing covers: cover_letter IS NULL OR cover_letter_generated_at IS NULL

    Also provides per-candidate breakdown for debugging.
    """
    SKIP_STATUSES = ["sent", "bounced", "error"]
    logger.info("check_cover_letter_status_task_started")

    async def _run():
        from sqlalchemy import func, select

        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Candidate, Job

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            from sqlalchemy import Integer  # needed for .cast(Integer) below
            # Get total count of non-terminal jobs
            total_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
            )
            total_jobs = total_result.scalar() or 0

            # Get count of jobs with missing covers
            missing_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(
                    (Job.cover_letter.is_(None)) |
                    (Job.cover_letter_generated_at.is_(None))
                )
            )
            missing_covers = missing_result.scalar() or 0

            # Get count of fresh covers (generated_at >= candidate.updated_at)
            fresh_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(Job.cover_letter.isnot(None))
                .where(Job.cover_letter_generated_at.isnot(None))
                .where(Job.candidate_id.isnot(None))
                .where(Candidate.id == Job.candidate_id)
                .where(Job.cover_letter_generated_at >= Candidate.updated_at)
            )
            fresh_covers = fresh_result.scalar() or 0

            # Get count of stale covers (generated_at < candidate.updated_at)
            stale_result = await session.execute(
                select(func.count(Job.id))
                .where(Job.status.notin_(SKIP_STATUSES))
                .where(Job.cover_letter.isnot(None))
                .where(Job.cover_letter_generated_at.isnot(None))
                .where(Job.candidate_id.isnot(None))
                .where(Candidate.id == Job.candidate_id)
                .where(Job.cover_letter_generated_at < Candidate.updated_at)
            )
            stale_covers = stale_result.scalar() or 0

            # Get per-candidate breakdown
            candidate_stats_result = await session.execute(
                select(
                    Candidate.id,
                    Candidate.name,
                    func.count(Job.id).label("total"),
                    func.sum(
                        (Job.cover_letter.is_(None) | Job.cover_letter_generated_at.is_(None)).cast(Integer)
                    ).label("missing"),
                    func.sum(
                        (Job.cover_letter.isnot(None) & Job.cover_letter_generated_at.isnot(None) &
                         Job.candidate_id.isnot(None) & (Job.cover_letter_generated_at < Candidate.updated_at)).cast(Integer)
                    ).label("stale"),
                )
                .join(Job, Job.candidate_id == Candidate.id)
                .where(Job.status.notin_(SKIP_STATUSES))
                .group_by(Candidate.id, Candidate.name)
            )

            by_candidate = []
            for row in candidate_stats_result.all():
                candidate_total = row.total or 0
                candidate_missing = row.missing or 0
                candidate_stale = row.stale or 0
                candidate_fresh = candidate_total - candidate_missing - candidate_stale

                by_candidate.append({
                    "candidate_id": row.id,
                    "candidate_name": row.name,
                    "total": candidate_total,
                    "fresh": candidate_fresh,
                    "stale": candidate_stale,
                    "missing": candidate_missing,
                })

        # Calculate percentages and log summary
        checked_jobs = total_jobs
        stale_percentage = (stale_covers / checked_jobs * 100) if checked_jobs > 0 else 0
        missing_percentage = (missing_covers / checked_jobs * 100) if checked_jobs > 0 else 0

        logger.info(
            "check_cover_letter_status_task_complete",
            total_jobs=total_jobs,
            fresh_covers=fresh_covers,
            stale_covers=stale_covers,
            missing_covers=missing_covers,
            stale_percentage=round(stale_percentage, 2),
            missing_percentage=round(missing_percentage, 2),
            candidates_with_jobs=len(by_candidate),
        )

        return {
            "status": "ok",
            "total_jobs": total_jobs,
            "fresh_covers": fresh_covers,
            "stale_covers": stale_covers,
            "missing_covers": missing_covers,
            "stale_percentage": round(stale_percentage, 2),
            "missing_percentage": round(missing_percentage, 2),
            "by_candidate": by_candidate,
        }

    return _run_async(_run())


# ─────────────────────────────────────────────────────────────────────────────
# Batched cover-letter generation (rate-limit safe)
# ─────────────────────────────────────────────────────────────────────────────
# Flow:
#   enqueue_cover_letter_task   → pushes {job_id, candidate_id} onto Redis LIST
#                                  "batch:cover:pending" and triggers a flush.
#   flush_cover_batch_task      → pops up to GROQ_RPM items, processes them
#                                  sequentially (one Groq call each), reschedules
#                                  itself when items remain.
#
# This replaces the old "fire N workers in parallel" model that burned through
# the Groq RPM budget in seconds.

_BATCH_QUEUE_KEY = "batch:cover:pending"
_BATCH_FLUSH_LOCK_KEY = "batch:cover:flush_lock"
_BATCH_FLUSH_TTL = 65   # seconds — slightly longer than 1-minute window


async def _generate_and_save_cover(job_id: str, candidate_id: str) -> dict:
    """Run cover letter generation + DB update for a single job.  Async helper."""
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Candidate, Job
    from services.ai.observability import get_callback_handler, flush

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        candidate = await session.get(Candidate, candidate_id) if candidate_id else None

        if not job:
            return {"status": "skipped", "reason": "job not found"}

        if not candidate:
            from sqlalchemy import select
            fallback = await session.execute(
                select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
            )
            candidate = fallback.scalar_one_or_none()
            if not candidate:
                return {"status": "skipped", "reason": "no candidate"}

        handler = get_callback_handler(
            "batch_cover_letter",
            session_id=job_id,
            tags=["cover_letter", "batch"],
            metadata={"job_id": job_id, "candidate_id": candidate_id},
        )
        callbacks = [handler] if handler else None

        cover = await _fill_cover_letter(job, candidate, callbacks=callbacks)

        job.cover_letter = cover
        job.cover_letter_generated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if job.status in ("new", "filtered", "scoring"):
            job.status = "cover_generated"
        await session.commit()

    flush()
    return {"status": "ok", "job_id": job_id}


@celery_app.task(
    name="services.ai.tasks.enqueue_cover_letter_task",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    ignore_result=True,
)
def enqueue_cover_letter_task(
    self,
    job_id: str,
    candidate_id: str,
) -> dict:
    """Push a cover-letter request onto the Redis batch queue.

    Returns immediately after enqueuing so Celery workers are not blocked
    waiting for a Groq slot.  flush_cover_batch_task drains the queue at
    the configured GROQ_RPM rate.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_name=self.name, job_id=job_id)

    async def _run():
        import json
        from services.api.core.cache import get_redis

        r = await get_redis()
        if r is None:
            # Redis unavailable — fall back to direct generation
            logger.warning("batch_enqueue_redis_unavailable_fallback", job_id=job_id)
            return await _generate_and_save_cover(job_id, candidate_id)

        payload = json.dumps({"job_id": job_id, "candidate_id": candidate_id})
        queue_len = await r.rpush(_BATCH_QUEUE_KEY, payload)

        scheduled = await r.set(_BATCH_FLUSH_LOCK_KEY, 1, nx=True, ex=6)
        if scheduled:
            flush_cover_batch_task.apply_async(
                countdown=6, queue="jh_cover_letter_batch"
            )

        logger.info("cover_enqueued", job_id=job_id, queue_depth=queue_len)
        return {"status": "enqueued", "job_id": job_id, "queue_depth": queue_len}

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "enqueue_cover_letter_task_failed", exc, job_id=job_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="services.ai.tasks.flush_cover_batch_task",
    bind=True,
    max_retries=20,
    default_retry_delay=_BATCH_FLUSH_TTL,
    ignore_result=True,
)
def flush_cover_batch_task(self) -> dict:
    """Drain up to GROQ_RPM items from the cover-letter batch queue per minute.

    Items that cannot acquire a slot are re-queued and a follow-up flush is
    scheduled for the next window — no job is ever dropped.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(task_name=self.name)

    async def _run():
        import json
        from services.api.core.config import get_settings
        from services.api.core.cache import get_redis
        from services.ai.rate_limiter import get_least_used_key, acquire_groq_slot

        settings = get_settings()
        batch_size: int = getattr(settings, "groq_rpm", 10)

        r = await get_redis()
        if r is None:
            logger.warning("flush_cover_batch_redis_unavailable")
            return {"status": "skipped", "reason": "redis unavailable"}

        items = []
        for _ in range(batch_size):
            raw = await r.lpop(_BATCH_QUEUE_KEY)
            if raw is None:
                break
            items.append(json.loads(raw))

        if not items:
            return {"status": "ok", "processed": 0, "reason": "queue_empty"}

        remaining = await r.llen(_BATCH_QUEUE_KEY)
        if remaining > 0:
            scheduled = await r.set(
                _BATCH_FLUSH_LOCK_KEY, 1, nx=True, ex=_BATCH_FLUSH_TTL
            )
            if scheduled:
                flush_cover_batch_task.apply_async(
                    countdown=_BATCH_FLUSH_TTL, queue="jh_cover_letter_batch"
                )

        processed = 0
        deferred = []
        key_id = await get_least_used_key()

        for item in items:
            jid = item.get("job_id", "?")
            acquired, wait = await acquire_groq_slot(key_id)
            if not acquired:
                logger.debug("flush_slot_unavailable_deferring", job_id=jid, wait=wait)
                deferred.append(item)
                continue
            try:
                await _generate_and_save_cover(jid, item.get("candidate_id", ""))
                processed += 1
            except Exception as exc:
                log_exception(logger, "flush_cover_item_failed", exc, job_id=jid)
                deferred.append(item)

        if deferred:
            pipe = r.pipeline()
            for item in deferred:
                pipe.rpush(_BATCH_QUEUE_KEY, json.dumps(item))
            await pipe.execute()
            await r.set(_BATCH_FLUSH_LOCK_KEY, 1, nx=True, ex=_BATCH_FLUSH_TTL)
            flush_cover_batch_task.apply_async(
                countdown=_BATCH_FLUSH_TTL, queue="jh_cover_letter_batch"
            )

        logger.info(
            "flush_cover_batch_complete",
            processed=processed,
            deferred=len(deferred),
            remaining=remaining,
        )
        return {"status": "ok", "processed": processed, "deferred": len(deferred)}

    try:
        return _run_async(_run())
    except Exception as exc:
        log_exception(logger, "flush_cover_batch_task_failed", exc)
        raise self.retry(exc=exc)
