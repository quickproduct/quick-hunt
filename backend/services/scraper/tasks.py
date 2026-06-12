"""Celery scraping tasks."""

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog
from billiard.exceptions import SoftTimeLimitExceeded
from sqlalchemy import case as sqlalchemy_case
from sqlalchemy.orm.exc import StaleDataError

from services.common.async_utils import run_async as _run_async
from services.common.batch_publisher import BatchPublisher
from services.common.logging import log_exception
from services.common.placeholder_emails import (
    PLACEHOLDER_DOMAINS,
    PLACEHOLDER_EMAILS,
    is_placeholder_email,
)
from services.scraper.celery_app import celery_app, get_adapter_registry
from services.common.cron_validators import cron_safe
from services.common.cron_monitor import cron_monitored

logger = structlog.get_logger(__name__)


def _naive_utc(dt):
    if dt is None:
        return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ #
# PHP / Laravel + Python / Django relevance filter                     #
# ------------------------------------------------------------------ #

# Fast title-only pre-check — these words in the title almost always mean a relevant role.
_RELEVANT_TITLE_KEYWORDS = frozenset(
    {
        # PHP stack
        "php",
        "laravel",
        "codeigniter",
        "symfony",
        "lumen",
        # Python stack
        "python",
        "django",
        "fastapi",
        "flask",
    }
)

# Full keyword set for title + description check.
_RELEVANT_KEYWORDS = frozenset(
    {
        # ── PHP: Core language / primary frameworks ───────────────────────────
        "php",
        "laravel",
        "php developer",
        "laravel developer",
        "backend php",
        "php backend",
        "laravel backend",
        "php engineer",
        "laravel engineer",
        "php programmer",
        "php web developer",
        "php full stack",
        "php fullstack",
        # PHP: Secondary frameworks
        "codeigniter",
        "symfony",
        "lumen",
        "yii",
        "cakephp",
        "cake php",
        "zend",
        "slim framework",
        "phalcon",
        "fuelphp",
        "fuel php",
        # PHP: Ecosystem tech
        "php mvc",
        "rest api php",
        "php api",
        "php artisan",
        "eloquent",
        "eloquent orm",
        "blade template",
        "blade templating",
        "composer php",
        "php mysql",
        "php pdo",
        "php laravel mysql",
        "laravel nova",
        "laravel forge",
        "laravel vapor",
        # PHP: Role title variants
        "backend developer php",
        "web developer php",
        "full stack php",
        "senior php",
        "junior php",
        "mid level php",
        "php lead",
        "php architect",
        # ── Python: Core language / primary frameworks ────────────────────────
        "python",
        "django",
        "fastapi",
        "flask",
        "python developer",
        "django developer",
        "fastapi developer",
        "flask developer",
        "backend python",
        "python backend",
        "django backend",
        "python engineer",
        "django engineer",
        "python programmer",
        "python web developer",
        "python full stack",
        "python fullstack",
        # Python: Ecosystem tech
        "rest api python",
        "python api",
        "sqlalchemy",
        "pydantic",
        "celery python",
        "python django",
        "django rest framework",
        "drf",
        "python flask",
        "aiohttp",
        "uvicorn",
        "gunicorn python",
        "python microservices",
        "python asyncio",
        # Python: Role title variants
        "backend developer python",
        "web developer python",
        "full stack python",
        "senior python",
        "junior python",
        "mid level python",
        "python lead",
        "python architect",
        "senior django",
        "junior django",
    }
)

# ── Broader backend / engineering keywords (non-PHP/Python roles) ───────────
# Jobs matching these but NOT the PHP/Python sets above are still accepted
# into the pipeline — they receive a static cover letter instead of an
# LLM-generated one.  This captures roles like Java backend, .NET backend,
# Go backend, general "software engineer", etc. that often have real HR emails.
_BROADER_BACKEND_KEYWORDS = frozenset(
    {
        "backend developer",
        "backend engineer",
        "back-end developer",
        "back-end engineer",
        "back end developer",
        "back end engineer",
        "web developer",
        "web engineer",
        "software engineer",
        "software developer",
        "full stack developer",
        "fullstack developer",
        "full stack engineer",
        "fullstack engineer",
        "full-stack developer",
        "full-stack engineer",
        "api developer",
        "senior developer",
        "senior engineer",
        "lead developer",
        "lead engineer",
        "tech lead",
        "software architect",
        "application developer",
        "platform engineer",
        "systems engineer",
        "systems developer",
        "server-side developer",
        "server side developer",
        "node developer",
        "nodejs developer",
        "node.js developer",
        "java developer",
        "java engineer",
        "java backend",
        ".net developer",
        ".net engineer",
        "c# developer",
        "golang developer",
        "go developer",
        "go engineer",
        "rust developer",
        "rust engineer",
        "ruby developer",
        "rails developer",
        "ruby on rails",
    }
)

# Titles that are clearly NOT engineering roles — always reject.
_EXCLUDED_TITLE_KEYWORDS = frozenset(
    {
        "sales",
        "marketing",
        "designer",
        "graphic",
        "hr manager",
        "human resources",
        "recruiter",
        "accounting",
        "finance manager",
        "operations manager",
        "project manager",
        "product manager",
        "business analyst",
        "data entry",
        "customer support",
        "customer service",
        "content writer",
        "copywriter",
        "social media",
        "seo",
        "administrative",
        "executive assistant",
        "office manager",
        "qa tester",
        "manual tester",
        "delivery driver",
        "warehouse",
        "intern",
        "apprentice",
        "consultant",
        "trainer",
        "teacher",
        "professor",
        "nurse",
        "doctor",
        "mechanical",
        "civil engineer",
        "electrical engineer",
    }
)


# Portals whose results are already filtered to relevant jobs at the source.
# RemoteOK: queried with ?tags=php or ?tags=python; WorkingNomads/WeWorkRemotely/
# Jobspresso: queried with specific job titles — results are trusted without re-checking.
_TRUSTED_PORTALS: frozenset[str] = frozenset({
    "remoteok",
    "workingnomads",
    "weworkremotely",
    "jobspresso",
    # Indian portals: Naukri API queried with job_title (e.g. "PHP Developer",
    # "Python Developer"). Shine SSR results are queried with a role-specific URL slug.
    "naukri",
    "shine",
})

# Keep old name as alias so any external code importing it still compiles.
_TRUSTED_PHP_PORTALS = _TRUSTED_PORTALS


def _is_relevant_job(job_data: dict) -> tuple[bool, bool]:
    """Return (is_relevant, is_php_python) for a job.

    Three tiers:
      1. PHP/Python keyword match  → (True, True)   — LLM cover letter path
      2. Broader backend/engineering keyword match → (True, False) — static cover letter path
      3. No match or excluded title → (False, False) — discarded

    Trusted portals (searched with role-specific terms) bypass the keyword
    filter and default to is_php_python=True.
    """
    title = (job_data.get("job_title") or "").lower()
    description = (job_data.get("job_description") or "").lower()

    # Reject clearly non-engineering titles first
    if any(kw in title for kw in _EXCLUDED_TITLE_KEYWORDS):
        return False, False

    # Trusted portals are pre-filtered at the source — accept as PHP/Python.
    if job_data.get("source_portal") in _TRUSTED_PORTALS:
        return True, True

    # Stage 1: fast title-only check for PHP/Python
    if any(kw in title for kw in _RELEVANT_TITLE_KEYWORDS):
        return True, True

    # Stage 2: full keyword scan of title + description for PHP/Python
    combined = title + " " + description
    if any(kw in combined for kw in _RELEVANT_KEYWORDS):
        return True, True

    # Stage 3: broader backend/engineering keyword check (non-PHP/Python)
    if any(kw in title for kw in _BROADER_BACKEND_KEYWORDS):
        return True, False

    if any(kw in combined for kw in _BROADER_BACKEND_KEYWORDS):
        return True, False

    return False, False


async def _save_job(job_data: dict, candidate_id: str | None) -> str | None:
    """Insert a single job into DB, skip duplicates. Returns job_id or None."""
    saved_ids = await _save_jobs_batch([job_data], candidate_id)
    return saved_ids[0] if saved_ids else None


async def _save_jobs_batch(
    jobs_data: list[dict],
    candidate_id: str | None,
) -> list[str]:
    """Bulk-insert jobs into DB, skipping duplicates and irrelevant jobs.

    Filters relevance and blacklisted companies in-memory first, then checks
    dedupe hashes in a single DB query, and finally bulk-inserts all new jobs
    in one transaction.  This is significantly faster than N individual inserts
    when scraping portals that return 50-100 jobs per page.

    Returns list of saved job IDs.
    """
    if not jobs_data:
        return []

    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from services.api.core.blacklist_utils import (
        get_blacklisted_names,
        is_company_blacklisted,
    )
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    # ── Stage 1: In-memory relevance filter (no DB work) ──────────────────
    relevant: list[dict] = []
    for jd in jobs_data:
        is_relevant, is_php_python = _is_relevant_job(jd)
        if is_relevant:
            jd["_is_php_python"] = is_php_python
            relevant.append(jd)
    dropped = len(jobs_data) - len(relevant)
    if dropped > 0:
        portal = jobs_data[0].get("source_portal", "unknown") if jobs_data else "unknown"
        logger.info(
            "jobs_filtered_irrelevant",
            portal=portal,
            total=len(jobs_data),
            dropped=dropped,
            kept=len(relevant),
        )
    if not relevant:
        return []

    # ── Stage 1.5: Date freshness filter (no DB work) ────────────────────
    from services.scraper.date_filter import filter_jobs_by_freshness, MAX_AGE_DAYS_HARD_CAP
    from services.api.core.config import get_settings

    _settings = get_settings()
    hard_cap = getattr(_settings, "max_job_age_days_hard_cap", MAX_AGE_DAYS_HARD_CAP)
    max_age_days = min(_settings.max_job_age_days, hard_cap)
    strict_mode = _settings.scrape_strict_date_mode

    try:
        from services.api.core.cache import cache_get
        override = await cache_get("admin:scrape_filter")
        if override and isinstance(override, dict):
            override_days = override.get("max_job_age_days", max_age_days)
            # Clamp admin override so the UI can never relax past 3 months.
            max_age_days = min(int(override_days), hard_cap)
            strict_mode = override.get("strict_date_mode", strict_mode)
    except Exception:
        pass

    portal_name = jobs_data[0].get("source_portal", "unknown") if jobs_data else "unknown"
    fresh, date_stats = filter_jobs_by_freshness(
        relevant,
        max_age_days=max_age_days,
        strict=strict_mode,
        portal=portal_name,
    )
    if date_stats.old_skipped > 0 or date_stats.date_unavailable > 0:
        logger.info(
            "jobs_filtered_by_date",
            **date_stats.to_dict(),
        )
    if not fresh:
        return []

    # ── Stage 1.6: Role keyword filter (PHP/Python only) ─────────────────
    if _settings.role_filter_enabled:
        from services.scraper.role_filter import is_target_role
        on_target: list[dict] = []
        role_dropped = 0
        for jd in fresh:
            if is_target_role(jd.get("job_title", ""), jd.get("job_description")):
                on_target.append(jd)
            else:
                role_dropped += 1
        if role_dropped:
            date_stats.role_filtered = role_dropped
            logger.info(
                "jobs_filtered_by_role",
                portal=portal_name,
                role_filtered=role_dropped,
                kept=len(on_target),
            )
        fresh = on_target
        if not fresh:
            return []

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        # ── Stage 2: Blacklist filter (single query) ──────────────────────
        blacklist = await get_blacklisted_names(session)
        filtered: list[dict] = []
        for jd in fresh:
            company = (jd.get("company") or "").strip()
            if is_company_blacklisted(company, blacklist):
                logger.info("job_skipped_blacklisted", company=company)
                continue
            filtered.append(jd)
        if not filtered:
            return []

        # ── Stage 3: Dedupe check (single query for all hashes) ───────────
        hashes = [jd["dedupe_hash"] for jd in filtered]
        existing_result = await session.execute(
            select(Job.dedupe_hash).where(Job.dedupe_hash.in_(hashes))
        )
        existing_hashes = {row[0] for row in existing_result.all()}

        # ── Stage 4: Bulk insert new jobs ─────────────────────────────────
        new_jobs: list[Job] = []
        for jd in filtered:
            if jd["dedupe_hash"] in existing_hashes:
                continue
            new_jobs.append(Job(
                id=str(uuid.uuid4()),
                candidate_id=candidate_id,
                job_title=jd["job_title"],
                company=jd["company"],
                location=jd.get("location"),
                job_description=jd.get("job_description"),
                job_url=jd["job_url"],
                posted_date=_naive_utc(jd.get("posted_date")),
                hr_email=jd.get("hr_email"),
                company_website=jd.get("company_website"),
                recruiter_name=jd.get("recruiter_name"),
                source_portal=jd["source_portal"],
                status="new",
                dedupe_hash=jd["dedupe_hash"],
                salary_min=jd.get("salary_min"),
                salary_max=jd.get("salary_max"),
                salary_currency=jd.get("salary_currency"),
                job_type=jd.get("job_type"),
                experience_required=jd.get("experience_required"),
                raw_data=jd.get("raw_data"),
                is_php_python=jd.get("_is_php_python", True),
            ))

        if not new_jobs:
            return []

        try:
            session.add_all(new_jobs)
            await session.commit()
            # Upsert hr_emails registry for any jobs that arrived with an email set
            from services.api.models.hr_email_utils import upsert_hr_email as _upsert_hr_email
            for _j in new_jobs:
                if _j.hr_email and _j.tenant_id:
                    await _upsert_hr_email(
                        session=session,
                        tenant_id=_j.tenant_id,
                        email=_j.hr_email,
                        increment_job_count=True,
                    )
            if any(_j.hr_email for _j in new_jobs):
                await session.commit()
            return [j.id for j in new_jobs]
        except IntegrityError:
            await session.rollback()
            saved = []
            for jd in filtered:
                if jd["dedupe_hash"] in existing_hashes:
                    continue
                try:
                    job = Job(
                        id=str(uuid.uuid4()),
                        candidate_id=candidate_id,
                        job_title=jd["job_title"],
                        company=jd["company"],
                        location=jd.get("location"),
                        job_description=jd.get("job_description"),
                        job_url=jd["job_url"],
                        posted_date=_naive_utc(jd.get("posted_date")),
                        hr_email=jd.get("hr_email"),
                        company_website=jd.get("company_website"),
                        recruiter_name=jd.get("recruiter_name"),
                        source_portal=jd["source_portal"],
                        status="new",
                        dedupe_hash=jd["dedupe_hash"],
                        salary_min=jd.get("salary_min"),
                        salary_max=jd.get("salary_max"),
                        salary_currency=jd.get("salary_currency"),
                        job_type=jd.get("job_type"),
                        experience_required=jd.get("experience_required"),
                        raw_data=jd.get("raw_data"),
                        is_php_python=jd.get("_is_php_python", True),
                    )
                    session.add(job)
                    await session.commit()
                    saved.append(job.id)
                except IntegrityError:
                    await session.rollback()
            return saved


async def _get_active_candidates() -> list[dict]:
    """Load all active candidates with target_roles."""
    from sqlalchemy import select

    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Candidate

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Candidate).where(Candidate.is_active == True)  # noqa
        )
        candidates = result.scalars().all()
        return [
            {
                "id": c.id,
                "target_roles": c.target_roles or [],
                "target_locations": c.target_locations or [],
            }
            for c in candidates
        ]


async def _update_search_task(
    task_id: str, updates: dict, increment_jobs: int = 0
) -> None:
    from sqlalchemy import select, update

    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import SearchTask

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        # Atomically increment jobs_found and tasks_completed
        await session.execute(
            update(SearchTask)
            .where(SearchTask.id == task_id)
            .values(
                jobs_found=SearchTask.jobs_found + increment_jobs,
                tasks_completed=SearchTask.tasks_completed + 1,
            )
        )
        await session.flush()

        # Only mark completed when ALL dispatched tasks have finished
        row = await session.execute(
            select(SearchTask.tasks_total, SearchTask.tasks_completed).where(
                SearchTask.id == task_id
            )
        )
        totals = row.first()
        if (
            totals
            and totals.tasks_total > 0
            and totals.tasks_completed >= totals.tasks_total
        ):
            non_count_updates = {
                k: v for k, v in updates.items() if k not in ("jobs_found",)
            }
            non_count_updates["status"] = "completed"
            await session.execute(
                update(SearchTask)
                .where(SearchTask.id == task_id)
                .values(**non_count_updates)
            )

        await session.commit()


# ------------------------------------------------------------------ #
# Main scraping task                                                   #
# ------------------------------------------------------------------ #
def _scrape_lock_key(portal: str, query_dict: dict, candidate_id: str | None) -> str:
    import hashlib
    import json
    payload = json.dumps(
        {"p": portal, "q": query_dict, "c": candidate_id},
        sort_keys=True, separators=(",", ":"),
    )
    digest = hashlib.sha1(payload.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"scrape:inflight:{portal}:{digest}"


_SCRAPE_LOCK_TTL = 2000  # > task hard limit (1920s) — auto-expires on crash

# Backpressure cap for jh_scraping_detail — discovery stops fanning out detail
# tasks past this depth so the queue can never grow unbounded again.
MAX_DETAIL_QUEUE_DEPTH = 2000


@celery_app.task(
    name="services.scraper.tasks.scrape_portal_task",
    bind=True,
    max_retries=3,
    soft_time_limit=300,  # 5 min — discovery only; detail fetches fan out to scrape_job_detail_task
    time_limit=360,
)
def scrape_portal_task(
    self,
    portal: str,
    query_dict: dict,
    candidate_id: str | None = None,
    auto_generate_covers: bool = False,
    search_task_id: str | None = None,
) -> dict:
    """Scrape a single portal for jobs matching query_dict.

    Dispatches generate_embedding_task for each new job found.
    If auto_generate_covers=True, also dispatches generate_cover_letter_task.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )
    logger.info("scrape_task_started", portal=portal, query=query_dict)

    registry = get_adapter_registry()
    if portal not in registry:
        logger.warning(
            "scrape_task_skipped_unknown_portal",
            portal=portal,
            valid_portals=list(registry.keys()),
        )
        return {"portal": portal, "saved": 0, "skipped": True, "reason": "unknown_portal"}

    lock_key = _scrape_lock_key(portal, query_dict, candidate_id)
    if not _run_async(_redis_set_nx(lock_key, self.request.id or "1", _SCRAPE_LOCK_TTL)):
        logger.info("scrape_task_skipped_inflight", portal=portal, lock_key=lock_key)
        return {"portal": portal, "saved": 0, "skipped": True, "reason": "inflight"}

    from services.scraper.base_adapter import JobQuery

    query = JobQuery(
        job_title=query_dict.get("job_title", ""),
        location=query_dict.get("location", "India"),
        max_results=query_dict.get("max_results", 50),
        candidate_id=candidate_id,
        auto_generate_covers=auto_generate_covers,
    )

    adapter = registry[portal]()

    async def _run():
        # Stage 1: discover — list jobs from the portal (cheap, one HTTP/Playwright call)
        raw_jobs = await adapter.search_jobs(query)
        if not raw_jobs:
            return 0

        # Stage 2: pre-dedupe — drop jobs whose dedupe_hash already exists in DB
        # BEFORE we pay the cost of a detail fetch. Single query, big savings.
        new_raw_jobs = await _filter_unseen_jobs(raw_jobs)
        dedup_dropped = len(raw_jobs) - len(new_raw_jobs)
        if not new_raw_jobs:
            logger.info(
                "scrape_portal_summary",
                portal=portal,
                total_scraped=len(raw_jobs),
                pre_dedup_dropped=dedup_dropped,
                saved=0,
                fanned_out=0,
            )
            return 0

        # Stage 3: split into "complete" (has description) vs "needs detail".
        # Complete jobs are saved here in one batch — no fan-out needed.
        # Needs-detail jobs are dispatched as parallel scrape_job_detail_task
        # so the discover task stays fast and detail work scales horizontally.
        complete: list[dict] = []
        needs_detail: list[dict] = []
        for rj in new_raw_jobs:
            payload = _raw_job_to_payload(rj)
            (complete if rj.job_description else needs_detail).append(payload)

        saved_job_ids = await _save_jobs_batch(complete, candidate_id) if complete else []

        # Stage 4: fan out detail fetches as individual tasks.
        # Backpressure: detail tasks drain far slower than discovery produces
        # them (a single Playwright pod manages ~0.2 tasks/s), so an unbounded
        # fan-out grows jh_scraping_detail without limit (observed at 144k).
        # Skipped jobs are not saved, so the next scrape cycle re-discovers
        # them and fans out when the queue has capacity.
        if needs_detail:
            detail_depth = await _get_queue_depth("jh_scraping_detail")
            if detail_depth is not None and detail_depth > MAX_DETAIL_QUEUE_DEPTH:
                logger.warning(
                    "detail_fanout_skipped_queue_full",
                    portal=portal,
                    queue_depth=detail_depth,
                    max_depth=MAX_DETAIL_QUEUE_DEPTH,
                    skipped=len(needs_detail),
                )
                needs_detail = []

        if needs_detail:
            bp = BatchPublisher(chunk_size=50)
            for payload in needs_detail:
                bp.add(scrape_job_detail_task.s(
                    raw_job_payload=payload,
                    candidate_id=candidate_id,
                    auto_generate_covers=auto_generate_covers,
                ))
            bp.flush_with_stagger(base_countdown=1, stagger_seconds=0.05)

        # Stage 5: enqueue downstream for jobs saved in this task
        if saved_job_ids:
            from services.ai.tasks import generate_embedding_task, score_job_task

            bp = BatchPublisher(chunk_size=50)
            for job_id in saved_job_ids:
                bp.add(generate_embedding_task.s(job_id))
                if candidate_id:
                    bp.add(score_job_task.s(job_id, candidate_id))
            bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)

        logger.info(
            "scrape_portal_summary",
            portal=portal,
            total_scraped=len(raw_jobs),
            pre_dedup_dropped=dedup_dropped,
            saved=len(saved_job_ids),
            fanned_out=len(needs_detail),
        )
        return len(saved_job_ids) + len(needs_detail)

    try:
        result = _run_async(_run())
        saved_count = result if isinstance(result, int) else 0
    except SoftTimeLimitExceeded as exc:
        logger.warning(
            "scrape_task_timeout",
            portal=portal,
            elapsed_soft_limit=self.soft_time_limit,
        )
        if search_task_id:
            _run_async(
                _update_search_task(
                    search_task_id, {"status": "error", "error": f"Scrape timed out for portal {portal}"}
                )
            )
        _run_async(_redis_delete(lock_key))
        retry_delay = min(60 * (2**self.request.retries), 240) + random.randint(0, 30)
        raise self.retry(exc=exc, countdown=retry_delay)
    except Exception as exc:
        log_exception(logger, "scrape_task_failed", exc, portal=portal)
        if search_task_id:
            _run_async(
                _update_search_task(
                    search_task_id, {"status": "error", "error": str(exc)}
                )
            )
        _run_async(_redis_delete(lock_key))
        # Exponential backoff with jitter: 60s, 120s, 240s (max 4 min), ±30s jitter
        retry_delay = min(60 * (2**self.request.retries), 240) + random.randint(0, 30)
        raise self.retry(exc=exc, countdown=retry_delay)
    finally:
        # Best-effort release on the happy path; SoftTimeLimitExceeded / generic
        # failure branches already released above before re-raising via retry().
        _run_async(_redis_delete(lock_key))

    if search_task_id:
        _run_async(
            _update_search_task(
                search_task_id,
                {"completed_at": _utcnow()},
                increment_jobs=saved_count,
            )
        )

    logger.info("scrape_task_complete", portal=portal, saved=saved_count)
    return {"portal": portal, "saved": saved_count}


# ------------------------------------------------------------------ #
# Discover/detail split helpers + scrape_job_detail_task               #
# ------------------------------------------------------------------ #

def _raw_job_to_payload(rj) -> dict:
    """Serialize a RawJob into a JSON-safe dict for Celery transport."""
    pd = rj.posted_date
    return {
        "job_title": rj.job_title,
        "company": rj.company,
        "location": rj.location,
        "job_description": rj.job_description,
        "job_url": rj.job_url,
        "posted_date": pd.isoformat() if pd is not None else None,
        "hr_email": rj.hr_email,
        "company_website": rj.company_website,
        "recruiter_name": rj.recruiter_name,
        "source_portal": rj.source_portal,
        "dedupe_hash": rj.dedupe_hash,
        "salary_min": rj.salary_min,
        "salary_max": rj.salary_max,
        "salary_currency": rj.salary_currency,
        "job_type": rj.job_type,
        "experience_required": rj.experience_required,
        "raw_data": rj.raw_data,
    }


def _payload_to_job_data(payload: dict) -> dict:
    """Inverse of _raw_job_to_payload — restores datetime, leaves the rest as-is."""
    out = dict(payload)
    pd = out.get("posted_date")
    if isinstance(pd, str):
        try:
            out["posted_date"] = datetime.fromisoformat(pd)
        except ValueError:
            out["posted_date"] = None
    return out


async def _filter_unseen_jobs(raw_jobs: list) -> list:
    """Return only RawJobs whose dedupe_hash is not already in the DB.

    Single SELECT for the whole batch — cheap. Saves expensive detail fetches
    on jobs we've already scraped on a prior run.
    """
    if not raw_jobs:
        return []
    from sqlalchemy import select
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    hashes = [rj.dedupe_hash for rj in raw_jobs if rj.dedupe_hash]
    if not hashes:
        return list(raw_jobs)

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(Job.dedupe_hash).where(Job.dedupe_hash.in_(hashes))
        )
        existing = {row[0] for row in result.all()}
    return [rj for rj in raw_jobs if rj.dedupe_hash not in existing]


@celery_app.task(
    name="services.scraper.tasks.scrape_job_detail_task",
    bind=True,
    max_retries=2,
    soft_time_limit=120,
    time_limit=180,
)
def scrape_job_detail_task(
    self,
    raw_job_payload: dict,
    candidate_id: str | None = None,
    auto_generate_covers: bool = False,
) -> dict:
    """Fetch the detail page for one job, persist it, dispatch downstream tasks.

    Spun out from scrape_portal_task: each portal scrape used to fetch N
    detail pages sequentially under a single 30-min task. Now each detail
    is its own short task that can run in parallel across workers.
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )

    portal = raw_job_payload.get("source_portal")
    url = raw_job_payload.get("job_url")
    registry = get_adapter_registry()
    if not portal or portal not in registry:
        logger.warning("detail_task_skipped_unknown_portal", portal=portal, url=url)
        return {"saved": 0, "skipped": True, "reason": "unknown_portal"}

    adapter = registry[portal]()

    async def _run() -> int:
        job_data = _payload_to_job_data(raw_job_payload)
        if not job_data.get("job_description"):
            try:
                detailed = await adapter.parse_job_detail(url)
                if detailed:
                    job_data["job_description"] = detailed.job_description
                    job_data["hr_email"] = job_data.get("hr_email") or detailed.hr_email
                    job_data["company_website"] = (
                        job_data.get("company_website") or detailed.company_website
                    )
            except Exception as exc:
                logger.warning("detail_fetch_failed", url=url, error=str(exc))

        saved_ids = await _save_jobs_batch([job_data], candidate_id)
        if saved_ids:
            from services.ai.tasks import generate_embedding_task, score_job_task
            bp = BatchPublisher(chunk_size=10)
            for job_id in saved_ids:
                bp.add(generate_embedding_task.s(job_id))
                if candidate_id:
                    bp.add(score_job_task.s(job_id, candidate_id))
            bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)
        return len(saved_ids)

    try:
        saved = _run_async(_run())
    except SoftTimeLimitExceeded as exc:
        logger.warning("detail_task_timeout", url=url, portal=portal)
        retry_delay = min(30 * (2**self.request.retries), 180) + random.randint(0, 15)
        raise self.retry(exc=exc, countdown=retry_delay)
    except Exception as exc:
        log_exception(logger, "detail_task_failed", exc, url=url, portal=portal)
        retry_delay = min(30 * (2**self.request.retries), 180) + random.randint(0, 15)
        raise self.retry(exc=exc, countdown=retry_delay)

    return {"saved": saved, "portal": portal, "url": url}


# ------------------------------------------------------------------ #
# MNC direct career-page scrape tasks                                  #
# ------------------------------------------------------------------ #
#
# Architecture (new, dispatch + fan-out):
#
#   dispatch_task  ──►  group(per-company tasks)  ──►  finalize_task
#   (lightweight)        (Playwright-capable,          (lightweight,
#                         KEDA scales 0→6)              releases lock)
#
# Per-tenant Redis lock prevents duplicate full scrapes.
# Per-company tasks save jobs + enqueue embeddings/scoring immediately,
# so partial progress survives any single-company failure or pod kill.
# ------------------------------------------------------------------ #

_MNC_LOCK_KEY = "mnc:scrape:lock:{tenant_id}"
_MNC_PROGRESS_KEY = "mnc:scrape:progress:{tenant_id}"
_MNC_LOCK_TTL = 3600  # 1 hour — self-heal on crashes


def _resolve_default_tenant_id() -> str:
    """Fallback tenant lookup for callers that don't pass one explicitly."""
    async def _fetch() -> str | None:
        from sqlalchemy import select
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Tenant  # type: ignore

        sf = get_worker_session_factory()
        async with sf() as session:
            row = (await session.execute(
                select(Tenant.id).order_by(Tenant.created_at.asc()).limit(1)
            )).first()
            return str(row[0]) if row else None
    try:
        tid = _run_async(_fetch())
        return tid or "default"
    except Exception:
        return "default"


async def _redis_set_nx(key: str, value: str, ttl: int) -> bool:
    """Try to acquire a Redis lock atomically. Returns True if acquired."""
    from services.api.core.cache import get_redis
    r = await get_redis()
    if r is None:
        # Fail-open: if Redis is unavailable we still allow the scrape,
        # mirroring the existing cache helpers' fail-open behaviour.
        return True
    try:
        return bool(await r.set(key, value, nx=True, ex=ttl))
    except Exception:
        return True


async def _redis_delete(key: str) -> None:
    from services.api.core.cache import get_redis
    r = await get_redis()
    if r is None:
        return
    try:
        await r.delete(key)
    except Exception:
        pass


async def _redis_hincrby(key: str, field: str, by: int = 1, ttl: int = _MNC_LOCK_TTL) -> None:
    from services.api.core.cache import get_redis
    r = await get_redis()
    if r is None:
        return
    try:
        await r.hincrby(key, field, by)
        await r.expire(key, ttl)
    except Exception:
        pass


async def _redis_hset(key: str, mapping: dict, ttl: int = _MNC_LOCK_TTL) -> None:
    from services.api.core.cache import get_redis
    r = await get_redis()
    if r is None:
        return
    try:
        await r.hset(key, mapping=mapping)
        await r.expire(key, ttl)
    except Exception:
        pass


# ── 1. Dispatcher task ────────────────────────────────────────────────
@celery_app.task(
    name="services.scraper.tasks.mnc_scrape_dispatch_task",
    bind=True,
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
)
def mnc_scrape_dispatch_task(
    self,
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    max_companies: int = 1000,
) -> dict:
    """Grab a per-tenant lock and fan out one Celery task per MNC company.

    Returns immediately after enqueuing the group; the chord callback
    `mnc_scrape_finalize_task` releases the lock when all per-company
    tasks finish (or fail individually).
    """
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )

    tid = tenant_id or _resolve_default_tenant_id()
    lock_key = _MNC_LOCK_KEY.format(tenant_id=tid)
    progress_key = _MNC_PROGRESS_KEY.format(tenant_id=tid)
    dispatch_id = self.request.id

    acquired = _run_async(_redis_set_nx(lock_key, dispatch_id, _MNC_LOCK_TTL))
    if not acquired:
        logger.info("mnc_scrape_dispatch_skipped_already_running", tenant_id=tid)
        return {"status": "already_running", "tenant_id": tid}

    from celery import chord, group
    from services.scraper.mnc_company_loader import load_active_mnc_companies

    companies = _run_async(load_active_mnc_companies(tid))
    if max_companies and max_companies < len(companies):
        companies = companies[:max_companies]

    if not companies:
        logger.warning("mnc_scrape_dispatch_no_companies", tenant_id=tid)
        # Release the lock immediately so the user can retry once they add rows.
        _run_async(_redis_delete(lock_key))
        return {"status": "no_companies", "tenant_id": tid, "dispatch_id": dispatch_id}

    total = len(companies)

    # Initialise progress hash so the status endpoint can show 0/total immediately.
    _run_async(_redis_hset(progress_key, {
        "dispatch_id": dispatch_id,
        "candidate_id": candidate_id or "",
        "total": total,
        "done": 0,
        "saved": 0,
        "started_at": _utcnow().isoformat(),
    }))

    header = group(
        mnc_scrape_company_task.s(
            company=company,
            candidate_id=candidate_id,
            tenant_id=tid,
            dispatch_id=dispatch_id,
        )
        for company in companies
    )
    callback = mnc_scrape_finalize_task.s(
        candidate_id=candidate_id,
        tenant_id=tid,
        dispatch_id=dispatch_id,
    )
    chord(header)(callback)

    logger.info("mnc_scrape_dispatched", tenant_id=tid, dispatch_id=dispatch_id, companies=total)
    return {
        "status": "queued",
        "tenant_id": tid,
        "dispatch_id": dispatch_id,
        "companies": total,
    }


# ── 2. Per-company task ───────────────────────────────────────────────
@celery_app.task(
    name="services.scraper.tasks.mnc_scrape_company_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    soft_time_limit=240,   # 4 min — mnc_career.py already wraps each call at 180s
    time_limit=300,
    acks_late=True,
)
def mnc_scrape_company_task(
    self,
    company: dict,
    candidate_id: str | None,
    tenant_id: str | None,
    dispatch_id: str,
) -> dict:
    """Scrape one MNC company, persist jobs immediately, dispatch embeddings + scoring."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
        dispatch_id=dispatch_id,
        company=company.get("name"),
    )

    from services.scraper.adapters.mnc_career import MNCCareerAdapter
    adapter = MNCCareerAdapter()
    progress_key = _MNC_PROGRESS_KEY.format(tenant_id=tenant_id or "default")

    async def _run() -> dict:
        # Use a per-task httpx client so workers don't share state.
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            try:
                raw_jobs = await asyncio.wait_for(
                    adapter._scrape_company(client, company),
                    timeout=180,
                )
            except asyncio.TimeoutError:
                logger.warning("mnc_company_timeout", company=company.get("name"))
                raw_jobs = []
            except Exception as exc:
                logger.warning("mnc_company_error", company=company.get("name"), error=str(exc))
                raw_jobs = []

        if not raw_jobs:
            await _redis_hincrby(progress_key, "done", 1)
            return {"company": company.get("name"), "saved": 0, "raw": 0}

        job_data_list = [
            {
                "job_title": j.job_title,
                "company": j.company,
                "location": j.location,
                "job_description": j.job_description,
                "job_url": j.job_url,
                "posted_date": j.posted_date,
                "hr_email": j.hr_email,
                "company_website": j.company_website,
                "recruiter_name": j.recruiter_name,
                "source_portal": j.source_portal,
                "dedupe_hash": j.dedupe_hash,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "salary_currency": j.salary_currency,
                "job_type": j.job_type,
                "experience_required": j.experience_required,
                "raw_data": j.raw_data,
            }
            for j in raw_jobs
        ]

        saved_job_ids = await _save_jobs_batch(job_data_list, candidate_id)
        saved_count = len(saved_job_ids)

        # Dispatch downstream immediately — no need to wait for the chord callback.
        if saved_job_ids:
            from services.ai.tasks import generate_embedding_task, score_job_task
            bp = BatchPublisher(chunk_size=50)
            for job_id in saved_job_ids:
                bp.add(generate_embedding_task.s(job_id))
                if candidate_id:
                    bp.add(score_job_task.s(job_id, candidate_id))
            bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)

        await _redis_hincrby(progress_key, "done", 1)
        if saved_count:
            await _redis_hincrby(progress_key, "saved", saved_count)

        return {
            "company": company.get("name"),
            "saved": saved_count,
            "raw": len(raw_jobs),
        }

    try:
        return _run_async(_run())
    except SoftTimeLimitExceeded:
        logger.warning("mnc_company_task_soft_timeout", company=company.get("name"))
        _run_async(_redis_hincrby(progress_key, "done", 1))
        return {"company": company.get("name"), "saved": 0, "raw": 0, "timeout": True}
    except Exception as exc:
        log_exception(logger, "mnc_company_task_failed", exc, company=company.get("name"))
        # Still mark done so the dispatcher's progress counter advances.
        try:
            _run_async(_redis_hincrby(progress_key, "done", 1))
        except Exception:
            pass
        return {"company": company.get("name"), "saved": 0, "raw": 0, "error": str(exc)}


# ── 3. Chord callback ─────────────────────────────────────────────────
@celery_app.task(
    name="services.scraper.tasks.mnc_scrape_finalize_task",
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def mnc_scrape_finalize_task(
    self,
    results: list[dict],
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    dispatch_id: str | None = None,
) -> dict:
    """Aggregate per-company results, release the Redis lock."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
        dispatch_id=dispatch_id,
    )

    total_saved = sum(int(r.get("saved", 0) or 0) for r in (results or []))
    total_raw = sum(int(r.get("raw", 0) or 0) for r in (results or []))
    companies = len(results or [])
    timeouts = sum(1 for r in (results or []) if r.get("timeout"))
    errors = sum(1 for r in (results or []) if r.get("error"))

    tid = tenant_id or _resolve_default_tenant_id()
    lock_key = _MNC_LOCK_KEY.format(tenant_id=tid)
    progress_key = _MNC_PROGRESS_KEY.format(tenant_id=tid)

    async def _finalize() -> None:
        await _redis_hset(progress_key, {
            "finished_at": _utcnow().isoformat(),
            "final_saved": total_saved,
            "final_raw": total_raw,
            "final_companies": companies,
            "final_timeouts": timeouts,
            "final_errors": errors,
        }, ttl=600)  # keep finished progress visible for 10 min
        await _redis_delete(lock_key)

    try:
        _run_async(_finalize())
    except Exception as exc:
        log_exception(logger, "mnc_scrape_finalize_redis_error", exc)

    logger.info(
        "mnc_scrape_finalize",
        tenant_id=tid,
        dispatch_id=dispatch_id,
        companies=companies,
        saved=total_saved,
        raw=total_raw,
        timeouts=timeouts,
        errors=errors,
    )
    return {
        "portal": "mnc_direct",
        "tenant_id": tid,
        "dispatch_id": dispatch_id,
        "companies": companies,
        "saved": total_saved,
        "raw": total_raw,
        "timeouts": timeouts,
        "errors": errors,
    }


# ── Backwards-compat shim ─────────────────────────────────────────────
@celery_app.task(
    name="services.scraper.tasks.scrape_mnc_jobs_task",
    bind=True,
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
)
def scrape_mnc_jobs_task(
    self,
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    max_companies: int = 1000,
) -> dict:
    """Legacy entry point — now just kicks off the dispatch task.

    Kept so any existing callers (cron, manual MCP, old API code-paths) continue to work.
    """
    res = mnc_scrape_dispatch_task.apply_async(
        kwargs={
            "candidate_id": candidate_id,
            "tenant_id": tenant_id,
            "max_companies": max_companies,
        },
        queue="jh_scraping_mnc_dispatch",
    )
    return {"status": "dispatched", "dispatch_task_id": res.id}


# ------------------------------------------------------------------ #
# Beat-scheduled task                                                  #
# ------------------------------------------------------------------ #

async def _get_queue_depth(queue_name: str) -> int | None:
    """Query RabbitMQ Management API for a queue's depth.

    Returns message count (ready + unacked), or None on failure.
    """
    import httpx
    from urllib.parse import urlparse, unquote, quote
    from services.api.core.config import get_settings

    settings = get_settings()
    rabbit_url = settings.rabbitmq_url
    if not rabbit_url or not rabbit_url.startswith(("amqp://", "amqps://")):
        return None

    try:
        parsed = urlparse(rabbit_url)
        host = parsed.hostname or "rabbitmq"
        user = unquote(parsed.username or "guest")
        password = unquote(parsed.password or "guest")
        vhost = unquote(parsed.path.lstrip("/")) or "/"
        vhost_encoded = quote(vhost, safe="")

        if rabbit_url.startswith("amqps://"):
            mgmt_url = f"https://{host}:443/api/queues/{vhost_encoded}/{queue_name}"
        else:
            mgmt_url = f"http://{host}:15672/api/queues/{vhost_encoded}/{queue_name}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(mgmt_url, auth=(user, password))
            if resp.status_code == 200:
                return resp.json().get("messages", 0) or 0
            logger.warning(
                "queue_depth_api_error",
                queue=queue_name,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return None
    except Exception as exc:
        logger.warning("queue_depth_failed", queue=queue_name, error=str(exc))
        return None


async def _get_realtime_queue_depth() -> int | None:
    return await _get_queue_depth("jh_scraping_realtime")


@celery_app.task(name="services.scraper.tasks.scheduled_scrape")
@cron_safe(
    task_name="scheduled_scrape",
    singleton_ttl_seconds=7200,  # 2h - matches cron interval
    max_runs_per_hour=1,  # Only once per 2-hour window
    max_queue_depth=5000,  # Don't scrape if too many pending jobs
    circuit_failure_threshold=3,
    circuit_recovery_seconds=3600,
)
@cron_monitored("scheduled_scrape")
def scheduled_scrape() -> dict:
    """Runs every 2 hours — reads active candidates, triggers search per candidate.

    auto_send is always False — never automatically send emails.

    Includes a pre-dispatch check on the jh_scraping_realtime queue depth to
    prevent accumulating unprocessable tasks when workers are backed up.
    """
    logger.info("scheduled_scrape_started")

    # ── Pre-dispatch: check jh_scraping_realtime queue depth ────────────────
    # If the realtime queue already has too many pending tasks, skip this
    # run entirely.  This prevents the 22K+ queue buildup scenario.
    MAX_REALTIME_DEPTH = 500
    realtime_depth = _run_async(_get_realtime_queue_depth())
    if realtime_depth is not None and realtime_depth > MAX_REALTIME_DEPTH:
        logger.warning(
            "scheduled_scrape_skipped_queue_full",
            queue="jh_scraping_realtime",
            depth=realtime_depth,
            max_depth=MAX_REALTIME_DEPTH,
        )
        return {
            "skipped": True,
            "reason": f"jh_scraping_realtime has {realtime_depth} tasks (max {MAX_REALTIME_DEPTH})",
            "queue_depth": realtime_depth,
        }

    candidates = _run_async(_get_active_candidates())
    tasks_dispatched = 0

    # Use only portals that have registered adapters — avoids ValueError
    # for disabled/intentionally-excluded portals (glassdoor, linkedin, etc.)
    all_portals = tuple(get_adapter_registry().keys())

    # Accumulate all scrape signatures and flush in batches of 50
    # instead of N×apply_async calls that flood the broker.
    bp = BatchPublisher(chunk_size=50)

    for candidate in candidates:
        roles = candidate.get("target_roles") or []
        locations = candidate.get("target_locations") or ["India"]
        candidate_id = candidate["id"]

        for role in roles:
            for loc in locations:
                for portal in all_portals:
                    bp.add(scrape_portal_task.s(
                        portal=portal,
                        query_dict={
                            "job_title": role,
                            "location": loc,
                            "max_results": 100,
                        },
                        candidate_id=candidate_id,
                        auto_generate_covers=True,
                    ))
                    tasks_dispatched += 1

    # Flush all accumulated tasks with staggered countdown to avoid thundering herd
    dispatched = bp.flush_with_stagger(base_countdown=1, stagger_seconds=0.05)

    logger.info(
        "scheduled_scrape_complete",
        tasks_dispatched=tasks_dispatched,
        batch_flushed=dispatched,
    )
    return {"tasks_dispatched": tasks_dispatched, "batch_flushed": dispatched}


# ------------------------------------------------------------------ #
# HR email backfill helpers                                           #
# ------------------------------------------------------------------ #

# Shared UA rotation list used by both DDG/Bing search and site crawl.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.4; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.6312.122 Safari/537.36 OPR/109.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; WOW64; Trident/7.0; rv:11.0) like Gecko",
]


async def _search_company_website(company: str) -> str | None:
    """Search for a company's official website via DuckDuckGo, falling back to Bing, then Google.

    Strategy:
    1. Try DuckDuckGo HTML search (no API key needed).
    2. On non-200 or no usable link found, wait 1 s then try Bing.
    3. On Bing failure, wait 1-2.5 s then try Google.
    Returns the first non-search-engine result URL, or None.
    """
    from bs4 import BeautifulSoup

    if not company or company.strip().lower() in ("unknown", ""):
        return None

    query = f"{company} official website contact email"
    headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0",
    }
    _skip_domains = {
        "duckduckgo.com",
        "bing.com",
        "google.com",
        "microsoft.com",
        "yahoo.com",
        "baidu.com",
        "yandex.com",
    }

    def _clean_url(href: str) -> str | None:
        """Return href if it looks like a real external site, else None."""
        if not href or not href.startswith("http"):
            return None
        from urllib.parse import urlparse

        try:
            netloc = urlparse(href).netloc.lower().lstrip("www.")
            if any(netloc == d or netloc.endswith("." + d) for d in _skip_domains):
                return None
        except Exception:
            return None
        return href

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        # ── 1. DuckDuckGo ─────────────────────────────────────────────────
        ddg_url: str | None = None
        try:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers=headers,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select("a.result__url"):
                    href = a.get("href", "")
                    if href and not href.startswith("http"):
                        href = "https://" + href
                    cleaned = _clean_url(href)
                    if cleaned:
                        ddg_url = cleaned
                        break
                if not ddg_url:
                    for a in soup.select("a.result__a"):
                        cleaned = _clean_url(a.get("href", ""))
                        if cleaned:
                            ddg_url = cleaned
                            break
            else:
                logger.warning("ddg_non_200", status=resp.status_code, company=company)
                if resp.status_code in (429, 403):
                    await asyncio.sleep(random.uniform(2.0, 5.0))  # back off before Bing
        except Exception as exc:
            logger.warning("ddg_search_error", company=company, error=str(exc))

        if ddg_url:
            return ddg_url

        # ── 2. Bing fallback ──────────────────────────────────────────────
        await asyncio.sleep(random.uniform(0.8, 2.0))  # polite gap between engines
        try:
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query},
                headers=headers,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                # Bing organic results: <li class="b_algo"> h2 > a
                for a in soup.select("li.b_algo h2 > a"):
                    cleaned = _clean_url(a.get("href", ""))
                    if cleaned:
                        logger.debug(
                            "bing_fallback_found", company=company, url=cleaned
                        )
                        return cleaned
            else:
                logger.warning("bing_non_200", status=resp.status_code, company=company)
        except Exception as exc:
            logger.warning("bing_search_error", company=company, error=str(exc))

        # ── 3. Google fallback ──────────────────────────────────────────
        await asyncio.sleep(random.uniform(1.0, 2.5))
        try:
            resp = await client.get(
                "https://www.google.com/search",
                params={"q": query},
                headers=headers,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "lxml")
                for a in soup.select("div.g a[href]"):
                    href = a.get("href", "")
                    if href.startswith("/url?q="):
                        from urllib.parse import parse_qs as _pqs, urlparse as _up
                        real_url = _pqs(_up(href).query).get("q", [None])[0]
                        cleaned = _clean_url(real_url)
                        if cleaned:
                            logger.debug(
                                "google_fallback_found",
                                company=company,
                                url=cleaned,
                            )
                            return cleaned
                    cleaned = _clean_url(href)
                    if cleaned:
                        return cleaned
            else:
                logger.warning(
                    "google_non_200", status=resp.status_code, company=company
                )
        except Exception as exc:
            logger.warning("google_search_error", company=company, error=str(exc))

    return None


def _derive_domain_from_company(company: str) -> str | None:
    """
    Guess a domain from a company name.
    e.g. "Funic Tech" → "funictech.com"
         "Boston Business Solutions" → "bostonbusinesssolutions.com"
    """
    import re

    if not company or company.lower() == "unknown":
        return None
    # Remove common suffixes that don't appear in domains
    cleaned = re.sub(
        r"\b(pvt|ltd|private|limited|inc|llc|llp|corp|corporation|technologies|technology|"
        r"solutions|services|software|systems|consulting|group|india|global)\b",
        "",
        company,
        flags=re.IGNORECASE,
    )
    # Keep only alphanumeric
    domain_part = re.sub(r"[^a-z0-9]", "", cleaned.lower()).strip()
    if len(domain_part) < 3:
        return None
    return f"{domain_part}.com"


async def _find_email_from_site(website: str) -> str | None:
    """Crawl common company pages concurrently for an HR email.

    Fetches all candidate pages in parallel, then picks the best email:
    HR-keyword match first (hr@, recruit@, careers@, …), then first found.
    """
    from urllib.parse import urlparse

    from services.scraper.base_adapter import extract_emails_from_text

    if not website:
        return None
    try:
        parsed = urlparse(website)
        base = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        return None

    pages = [
        website,
        f"{base}/contact",
        f"{base}/contact-us",
        f"{base}/about",
        f"{base}/about-us",
        f"{base}/careers",
        f"{base}/jobs",
        f"{base}/team",
        f"{base}/people",
        f"{base}/hr",
        f"{base}/work-with-us",
        f"{base}/recruitment",
        f"{base}/get-in-touch",
        f"{base}/hire-us",
        f"{base}/apply",
        f"{base}/reach-us",
        f"{base}/contactus",
        f"{base}/pages/contact",
        f"{base}/company/contact",
        f"{base}/en/contact",
        f"{base}/en/contact-us",
    ]
    hr_keywords = ["hr@", "recruit", "talent", "hiring", "careers@", "jobs@", "people@"]
    _headers = {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    _contact_kw = {"contact", "hr", "career", "recruit", "hiring", "team", "about", "people", "reach"}

    async def _fetch_page(client: httpx.AsyncClient, page_url: str) -> tuple[str, list[str]]:
        """Return (html, emails) for page_url, or ('', []) on any failure."""
        try:
            resp = await client.get(page_url, headers=_headers)
            if resp.status_code == 200:
                return resp.text, extract_emails_from_text(resp.text)
        except Exception:
            pass
        return "", []

    async def _discover_extra_pages(homepage_html: str) -> list[str]:
        """Parse homepage <a> links and return up to 5 internal contact-related URLs."""
        if not homepage_html:
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(homepage_html, "lxml")
            extra: list[str] = []
            seen = set(pages)
            for a in soup.find_all("a", href=True):
                href: str = a["href"].strip()
                if href.startswith("#") or href.lower().startswith("mailto:"):
                    continue
                if href.startswith("/"):
                    full = base + href
                elif href.startswith("http"):
                    full = href
                else:
                    continue
                # only same-origin links with a contact-related path segment
                from urllib.parse import urlparse as _up
                path = _up(full).path.lower()
                if _up(full).netloc and _up(full).netloc != _up(base).netloc:
                    continue
                if any(kw in path for kw in _contact_kw) and full not in seen:
                    extra.append(full)
                    seen.add(full)
                if len(extra) >= 5:
                    break
            return extra
        except Exception:
            return []

    async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
        # Fetch all fixed pages; keep homepage html for link discovery
        page_results = await asyncio.gather(
            *[_fetch_page(client, p) for p in pages], return_exceptions=True
        )
        # Discover extra pages from homepage response (first item)
        homepage_html = page_results[0][0] if page_results and isinstance(page_results[0], tuple) else ""
        extra_pages = await _discover_extra_pages(homepage_html)
        if extra_pages:
            extra_results = await asyncio.gather(
                *[_fetch_page(client, p) for p in extra_pages], return_exceptions=True
            )
        else:
            extra_results = []

    all_results = list(page_results) + list(extra_results)

    # First pass: prefer HR-keyword emails from any page
    fallback: str | None = None
    for res in all_results:
        if isinstance(res, tuple):
            _, emails = res
        elif isinstance(res, list):
            emails = res
        else:
            continue
        for email in emails:
            if any(kw in email.lower() for kw in hr_keywords):
                return email
            if fallback is None:
                fallback = email

    return fallback


async def _check_mx_record(domain: str) -> bool:
    """Return True if domain has MX records."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        records = await loop.run_in_executor(None, _resolve_mx_sync, domain)
        return bool(records)
    except Exception:
        return True  # fail-open


def _resolve_mx_sync(domain: str) -> list:
    try:
        import dns.resolver  # type: ignore[import]
        return list(dns.resolver.resolve(domain, "MX"))
    except Exception:
        return []


# ── Company domain Redis cache ──────────────────────────────────────────────
# Avoids re-querying DDG for the same company on every backfill run.
# Cache key: "company:domain:{company_name_lowercase}"  TTL: 7 days
_COMPANY_DOMAIN_CACHE_PREFIX = "company:domain:"
_COMPANY_DOMAIN_CACHE_TTL = 604800  # 7 days


async def _get_cached_company_domain(company: str) -> str | None:
    """Return previously discovered domain for a company, or None if not cached."""
    import redis.asyncio as aioredis
    from services.api.core.config import get_settings

    try:
        settings = get_settings()
        r = aioredis.from_url(
            settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        key = f"{_COMPANY_DOMAIN_CACHE_PREFIX}{company.lower().strip()}"
        value = await r.get(key)
        await r.aclose()
        return value
    except Exception:
        return None


async def _set_cached_company_domain(company: str, website: str) -> None:
    """Cache a discovered company website domain for 7 days."""
    import redis.asyncio as aioredis
    from services.api.core.config import get_settings

    try:
        settings = get_settings()
        r = aioredis.from_url(
            settings.redis_url, decode_responses=True, socket_timeout=2, socket_connect_timeout=2
        )
        key = f"{_COMPANY_DOMAIN_CACHE_PREFIX}{company.lower().strip()}"
        await r.setex(key, _COMPANY_DOMAIN_CACHE_TTL, website)
        await r.aclose()
    except Exception:
        pass


def _extract_company_from_description(description: str) -> str | None:
    """Extract company name from job description text when company field is Unknown."""
    import re

    if not description:
        return None
    # "About CompanyName" at start of paragraph
    m = re.search(
        r"(?:^|\n)About\s+([A-Z][A-Za-z0-9\s&.,'-]{2,50}?)(?:\n|:|\?|$)", description
    )
    if m:
        return m.group(1).strip().rstrip(".,:")
    # "[CompanyName] is hiring / is looking / is a"
    m = re.search(
        r"^([A-Z][A-Za-z0-9\s&.'-]{2,40}?)\s+(?:is hiring|is looking|is a |are looking|are hiring)",
        description,
    )
    if m:
        return m.group(1).strip()
    return None


_GUESS_SKIP_DOMAINS = {
    # Job boards / aggregators — guessing hr@jobboard.com is always wrong
    "indeed.com",
    "in.indeed.com",
    "linkedin.com",
    "glassdoor.com",
    "monster.com",
    "ziprecruiter.com",
    "careerbuilder.com",
    "dice.com",
    "simplyhired.com",
    "naukri.com",
    "shine.com",
    "foundit.in",
    "timesjobs.com",
    "internshala.com",
    "wellfound.com",
    "lever.co",
    "greenhouse.io",
    "workday.com",
    "icims.com",
    "taleo.net",
    "brassring.com",
    "smartrecruiters.com",
    # Disposable / placeholder domains — never valid HR addresses
    "example.com",
    "example.org",
    "example.net",
    "sentry.io",
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.com",
    "10minutemail.com",
    "yopmail.com",
    "trashmail.com",
}


_HR_EMAIL_PREFIXES = ["hr", "careers", "recruit", "talent", "hiring", "jobs", "people"]

# Tri-state SMTP probe result
SMTP_VERIFIED = "verified"     # mailbox exists (250/251/252)
SMTP_REJECTED = "rejected"     # mailbox does not exist (5xx)
SMTP_UNVERIFIED = "unverified"  # timeout / unknown code / no MX — DO NOT trust


async def _smtp_probe_email(email: str, domain: str) -> str:
    """SMTP probe — tri-state result.

    Connects to the domain's MX server and issues RCPT TO without sending
    any message. Returns SMTP_VERIFIED only on a definitive 2xx accept.
    Timeouts, unknown codes, and missing MX return SMTP_UNVERIFIED so the
    caller can refuse to persist the candidate as a real HR email.

    250/251/252 → SMTP_VERIFIED
    550/551/552/553/554 → SMTP_REJECTED
    anything else (timeout, no MX, conn refused) → SMTP_UNVERIFIED
    """
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        mx_records = await loop.run_in_executor(None, _resolve_mx_sync, domain)
        if not mx_records:
            return SMTP_UNVERIFIED
        mx_host = str(sorted(mx_records, key=lambda r: r.preference)[0].exchange).rstrip(".")
    except Exception:
        return SMTP_UNVERIFIED

    async def _probe() -> str:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(mx_host, 25), timeout=5
            )

            async def _readline() -> str:
                return (await asyncio.wait_for(reader.readline(), timeout=5)).decode(errors="ignore").strip()

            async def _send(cmd: str) -> str:
                writer.write((cmd + "\r\n").encode())
                await writer.drain()
                return await _readline()

            await _readline()  # banner
            await _send("EHLO probe.example.com")
            await _readline()
            await _send("MAIL FROM:<probe@example.com>")
            resp = await _send(f"RCPT TO:<{email}>")
            writer.write(b"QUIT\r\n")
            await writer.drain()
            writer.close()
            code = int(resp[:3]) if resp[:3].isdigit() else 0
            if code in (250, 251, 252):
                return SMTP_VERIFIED
            if code in (550, 551, 552, 553, 554):
                return SMTP_REJECTED
            return SMTP_UNVERIFIED
        except Exception:
            return SMTP_UNVERIFIED

    try:
        return await asyncio.wait_for(_probe(), timeout=10)
    except Exception:
        return SMTP_UNVERIFIED


async def _guess_emails_from_domain(domain: str) -> str | None:
    """Return a verified HR email for the domain, or None.

    Tries common HR prefixes in order, requiring SMTP_VERIFIED before
    returning. Never falls back to an unverified guess — fake addresses
    are the primary source of bounces.
    """
    if not domain:
        return None
    bare = domain.lstrip("www.")
    if any(bare == d or bare.endswith("." + d) for d in _GUESS_SKIP_DOMAINS):
        return None

    for prefix in _HR_EMAIL_PREFIXES:
        candidate = f"{prefix}@{domain}"
        if await _smtp_probe_email(candidate, domain) == SMTP_VERIFIED:
            return candidate

    return None


async def _discover_email_for_job(
    job_id: str,
    job_title: str,
    company: str,
    job_description: str | None,
    company_website: str | None,
    job_url: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """
    Full email discovery pipeline. Returns (email, company_name, website) — any can be None.

    Steps:
    1. Extract email directly from job description text
    2. Resolve real company name if stored as "Unknown"
       a. Parse cmp= param from Indeed job URL
       b. Extract from first lines of description
    3. Crawl stored company_website pages for email (rotating UA + homepage link discovery)
    4. DDG-search for company website → crawl it
    5. Multi-pattern guess (hr/careers/recruit/talent/…) + SMTP probe to verify

    Each step is timed and logged for pipeline health monitoring.
    """
    import asyncio
    import re
    import time as _time
    from urllib.parse import parse_qs, urlparse

    from services.scraper.base_adapter import extract_emails_from_text

    _t0 = _time.monotonic()
    _step_timings: list[str] = []  # e.g. ["step1:0ms", "step3:450ms"]
    _step_results: list[str] = []  # e.g. ["step1:skip", "step3:fail", "step4:skip"]

    def _elapsed_ms() -> int:
        return int((_time.monotonic() - _t0) * 1000)

    # ── 1. Extract email directly from description ────────────────────
    if job_description:
        emails = extract_emails_from_text(job_description)
        if emails:
            logger.info("email_found_in_description", job_id=job_id, email=emails[0], step=1)
            return emails[0], None, None
        _step_results.append("step1:fail")
    else:
        _step_results.append("step1:skip(no_desc)")
    _step_timings.append(f"step1:{_elapsed_ms()}ms")

    # ── 2. Resolve company name when "Unknown" ────────────────────────
    resolved_company = company
    if not resolved_company or resolved_company.lower() == "unknown":
        # 2a. Extract from Indeed URL cmp= param
        if job_url:
            try:
                qs = parse_qs(urlparse(job_url).query)
                cmp = qs.get("cmp", [None])[0]
                if cmp:
                    resolved_company = cmp.replace("-", " ").replace("+", " ").strip()
                    logger.info(
                        "company_from_url", job_id=job_id, company=resolved_company
                    )
            except Exception:
                pass
        # 2b. Extract from description text
        if (
            not resolved_company or resolved_company.lower() == "unknown"
        ) and job_description:
            extracted = _extract_company_from_description(job_description)
            if extracted:
                resolved_company = extracted
                logger.info(
                    "company_from_description", job_id=job_id, company=resolved_company
                )
        if not resolved_company or resolved_company.lower() == "unknown":
            _step_results.append("step2:fail(still_unknown)")
        else:
            _step_results.append("step2:resolved")
    else:
        _step_results.append("step2:skip(known)")
    _step_timings.append(f"step2:{_elapsed_ms()}ms")

    website = company_website

    # ── 3. Crawl stored company website ──────────────────────────────
    if website:
        email = await _find_email_from_site(website)
        if email:
            logger.info(
                "email_found_on_site", job_id=job_id, email=email, source=website, step=3
            )
            return email, resolved_company, website
        _step_results.append("step3:fail")
    else:
        _step_results.append("step3:skip(no_website)")
    _step_timings.append(f"step3:{_elapsed_ms()}ms")

    # ── 4. DDG-search for company website (with Redis cache) ─────────
    if not website and resolved_company and resolved_company.lower() != "unknown":
        cached_site = await _get_cached_company_domain(resolved_company)
        if cached_site:
            website = cached_site
            logger.debug(
                "website_from_cache", job_id=job_id, company=resolved_company
            )
        else:
            website = await _search_company_website(resolved_company)
            await asyncio.sleep(random.uniform(0.5, 1.5))  # DDG rate limit (with jitter)
            if website:
                await _set_cached_company_domain(resolved_company, website)
                logger.info(
                    "website_found_via_ddg",
                    job_id=job_id,
                    company=resolved_company,
                    website=website,
                )
            else:
                _step_results.append("step4:fail(ddg+bing)")
    elif website:
        _step_results.append("step4:skip(has_website)")
    else:
        _step_results.append("step4:skip(unknown_company)")

    # ── 4b. Derive domain from company name when DDG fails ────────────
    if not website and resolved_company and resolved_company.lower() != "unknown":
        derived = _derive_domain_from_company(resolved_company)
        if derived:
            website = f"https://{derived}"
            logger.info(
                "website_derived_from_name",
                job_id=job_id,
                company=resolved_company,
                website=website,
            )
        else:
            _step_results.append("step4b:fail(cant_derive)")
    _step_timings.append(f"step4:{_elapsed_ms()}ms")

    if website:
        email = await _find_email_from_site(website)
        if email:
            logger.info(
                "email_found_via_site", job_id=job_id, email=email, website=website, step=4
            )
            return email, resolved_company, website
        _step_results.append("step4_crawl:fail")

        domain = urlparse(website).netloc
        if domain:
            # ── 5. Common pattern guess with SMTP probe ───────────────
            guessed = await _guess_emails_from_domain(domain)
            if guessed:
                logger.info(
                    "email_guessed_from_domain",
                    job_id=job_id,
                    email=guessed,
                    domain=domain,
                    step=5,
                )
                return guessed, resolved_company, website
            _step_results.append("step5:fail(no_guess)")
    else:
        _step_results.append("step5:skip(no_website)")

    _step_timings.append(f"step5:{_elapsed_ms()}ms")

    # Summary log for pipeline health monitoring — shows which steps ran
    # and total time.  This is critical for diagnosing why 200+ jobs
    # have no HR email (e.g. all failing at step 4 = DDG blocked).
    logger.info(
        "discovery_pipeline_complete",
        job_id=job_id,
        company=resolved_company or company,
        has_website=bool(website),
        has_description=bool(job_description),
        result="not_found",
        total_ms=_elapsed_ms(),
        steps=",".join(_step_timings),
        step_results=",".join(_step_results),
    )

    return None, resolved_company, website


# ------------------------------------------------------------------ #
# HR email discovery — shared constants                                #
# ------------------------------------------------------------------ #
# Maximum number of discovery attempts before marking a job as
# 'unreachable'.  Prevents the backfill from re-processing the same
# hopeless jobs on every cycle (the main cause of the 200+ backlog).
_HR_DISCOVERY_MAX_ATTEMPTS = 8



# ------------------------------------------------------------------ #
# Hourly HR email backfill task                                       #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.scraper.tasks.backfill_hr_emails_task",
)
@cron_safe(
    task_name="backfill_hr_emails_task",
    singleton_ttl_seconds=300,   # 5 min - matches new cron interval
    max_runs_per_hour=12,        # Every 5 min = 12/hour
    max_queue_depth=5000,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=1800,
)
@cron_monitored("backfill_hr_emails_task")
def backfill_hr_emails_task() -> dict:
    """
    Every 5 min — fetches jobs without HR email and attempts discovery via:
    1. Job description extraction
    2. Company website crawl (stored or DDG-discovered)
    3. Multi-pattern guess + SMTP probe

    Processes up to BATCH_SIZE jobs per run.
    Skips jobs with status: sent / bounced.
    Skips jobs that have exhausted _HR_DISCOVERY_MAX_ATTEMPTS.
    Priority order: cover_generated jobs first, then current-month, then rest.
    """
    BATCH_SIZE = 300  # 300 jobs × ~3s avg API latency with 25 concurrent coroutines
    MAX_ATTEMPTS = _HR_DISCOVERY_MAX_ATTEMPTS
    logger.info("backfill_hr_emails_started", batch_size=BATCH_SIZE, max_attempts=MAX_ATTEMPTS)

    async def _run():
        import asyncio
        from datetime import date

        from sqlalchemy import func, or_, select

        from services.api.core.blacklist_utils import (
            get_blacklisted_names,
            is_company_blacklisted,
        )
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job

        skip_statuses = ["sent", "bounced", "error"]

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            blacklist = await get_blacklisted_names(session)
            # Priority: cover_generated (blocked on sending) → current-month → rest.
            # Within each tier, fewest attempts first (new jobs ahead of repeatedly-failed).
            result = await session.execute(
                select(Job)
                .where(Job.hr_email.is_(None))
                .where(Job.status.notin_(skip_statuses))
                .where(
                    or_(
                        Job.hr_email_discovery_attempts.is_(None),
                        Job.hr_email_discovery_attempts < MAX_ATTEMPTS,
                    )
                )
                .order_by(
                    sqlalchemy_case(
                        (Job.status == "cover_generated", 0),
                        (
                            Job.posted_date >= func.date_trunc("month", func.current_date()),
                            1,
                        ),
                        else_=2,
                    ),
                    Job.hr_email_discovery_attempts.asc().nullsfirst(),
                    Job.scraped_at.asc(),
                )
                .limit(BATCH_SIZE)
            )
            jobs = result.scalars().all()

        # Filter out blacklisted companies - don't waste email-discovery API calls on them
        jobs = [
            j for j in jobs if not is_company_blacklisted(j.company or "", blacklist)
        ]
        logger.info("backfill_jobs_fetched", count=len(jobs))

        if not jobs:
            return {"found": 0, "not_found": 0, "unreachable": 0, "total": 0}

        # Process up to 25 jobs concurrently.
        # Most time is I/O-bound (HTTP to DDG/Bing/Google + site crawls), not DB —
        # 25 concurrent coroutines saturate the network pipeline while
        # DB writes (brief sessions) stay well within pool limits.
        sem = asyncio.Semaphore(25)

        # Per-domain locks prevent two concurrent coroutines from calling
        # paid APIs (Snov.io) for the same domain on the same run.
        _domain_locks: dict[str, asyncio.Lock] = {}

        async def _get_domain_lock(company_website: str | None) -> asyncio.Lock | None:
            if not company_website:
                return None
            from urllib.parse import urlparse as _up
            netloc = _up(company_website).netloc or company_website
            if netloc not in _domain_locks:
                _domain_locks[netloc] = asyncio.Lock()
            return _domain_locks[netloc]

        async def _process_job(job) -> str:
            """Returns 'found', 'not_found', or 'unreachable'."""
            async with sem:
                domain_lock = await _get_domain_lock(job.company_website)
                async with (domain_lock if domain_lock else asyncio.Lock()):
                    try:
                        (
                            email,
                            resolved_company,
                            resolved_website,
                        ) = await _discover_email_for_job(
                            job_id=job.id,
                            job_title=job.job_title,
                            company=job.company,
                            job_description=job.job_description,
                            company_website=job.company_website,
                            job_url=job.job_url,
                        )

                        async with session_factory() as session:
                            db_job = await session.get(Job, job.id)
                            if db_job:
                                new_attempts = (db_job.hr_email_discovery_attempts or 0) + 1
                                db_job.hr_email_discovery_attempts = new_attempts

                                if email:
                                    db_job.hr_email = email
                                    db_job.hr_email_discovery_status = "found"
                                    db_job.hr_email_discovered_at = _utcnow()
                                    from services.api.models.hr_email_utils import upsert_hr_email as _upsert_hr_email
                                    await _upsert_hr_email(
                                        session=session,
                                        tenant_id=db_job.tenant_id,
                                        email=email,
                                        increment_job_count=True,
                                    )
                                elif new_attempts >= MAX_ATTEMPTS:
                                    db_job.hr_email_discovery_status = "unreachable"
                                else:
                                    db_job.hr_email_discovery_status = "not_found"

                                if resolved_company and (
                                    not db_job.company
                                    or db_job.company.lower() == "unknown"
                                ):
                                    db_job.company = resolved_company
                                if resolved_website and not db_job.company_website:
                                    db_job.company_website = resolved_website
                                try:
                                    await session.commit()
                                except StaleDataError:
                                    logger.warning(
                                        "backfill_job_deleted_during_update",
                                        job_id=job.id,
                                        email_found=bool(email),
                                    )
                            else:
                                logger.warning(
                                    "backfill_job_deleted_during_update",
                                    job_id=job.id,
                                    email_found=bool(email),
                                )

                        if email:
                            logger.info(
                                "hr_email_updated",
                                job_id=job.id,
                                company=job.company,
                                email=email,
                            )
                            return "found"
                        else:
                            attempts = (job.hr_email_discovery_attempts or 0) + 1
                            if attempts >= MAX_ATTEMPTS:
                                logger.info(
                                    "hr_email_unreachable",
                                    job_id=job.id,
                                    company=resolved_company or job.company,
                                    attempts=attempts,
                                )
                                return "unreachable"
                            logger.debug(
                                "hr_email_not_found",
                                job_id=job.id,
                                company=resolved_company or job.company,
                                attempts=attempts,
                            )
                            return "not_found"

                    except Exception as exc:
                        log_exception(logger, "backfill_job_failed", exc, job_id=job.id)
                        return "not_found"
                    finally:
                        await asyncio.sleep(0.3)

        results = await asyncio.gather(*[_process_job(j) for j in jobs])
        found = results.count("found")
        not_found = results.count("not_found")
        unreachable = results.count("unreachable")

        logger.info(
            "backfill_hr_emails_complete",
            found=found, not_found=not_found, unreachable=unreachable,
        )
        return {
            "found": found,
            "not_found": not_found,
            "unreachable": unreachable,
            "total": len(jobs),
        }

    return _run_async(_run())



# ------------------------------------------------------------------ #



@celery_app.task(
    name="services.scraper.tasks.fix_placeholder_emails_task",
)
@cron_safe(
    task_name="fix_placeholder_emails_task",
    singleton_ttl_seconds=1800,  # 30 min - matches cron interval
    max_runs_per_hour=2,
    max_queue_depth=5000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=3600,
)
@cron_monitored("fix_placeholder_emails_task")
def fix_placeholder_emails_task() -> dict:
    """
    Every 30 min — finds jobs whose hr_email is a placeholder or junk value
    (Indeed/portal placeholder domains, Shine test emails, image filenames
    incorrectly parsed as emails, disposable email services, etc.), scrapes
    the company website to discover a real contact email, and updates hr_email.

    If no real email is found the placeholder is cleared (set to NULL)
    so the regular backfill_hr_emails_task will retry on the next cycle.
    """
    BATCH_SIZE = 50
    logger.info("fix_placeholder_emails_started", batch_size=BATCH_SIZE)

    async def _run():
        import asyncio

        from sqlalchemy import or_, select

        from services.api.core.blacklist_utils import (
            get_blacklisted_names,
            is_company_blacklisted,
        )
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job

        skip_statuses = ["sent", "bounced", "error"]

        # Domain-based placeholders (Indeed + disposable services)
        domain_filters = [
            Job.hr_email.ilike(f"%@{domain}") for domain in PLACEHOLDER_DOMAINS
        ]
        # Exact-match placeholder emails (Shine test email, etc.)
        exact_filters = [
            Job.hr_email == email for email in PLACEHOLDER_EMAILS
        ]
        # Image/CSS filename patterns — ilike is safe since these aren't valid TLDs
        image_filters = [
            Job.hr_email.ilike(f"%.{ext}") for ext in
            ("png", "jpg", "jpeg", "gif", "svg", "webp", "avif", "css", "js")
        ]

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            blacklist = await get_blacklisted_names(session)
            result = await session.execute(
                select(Job)
                .where(or_(*domain_filters, *exact_filters, *image_filters))
                .where(Job.status.notin_(skip_statuses))
                .order_by(Job.scraped_at.desc())
                .limit(BATCH_SIZE)
            )
            jobs = result.scalars().all()

        jobs = [
            j for j in jobs if not is_company_blacklisted(j.company or "", blacklist)
        ]
        logger.info("fix_placeholder_emails_fetched", count=len(jobs))

        if not jobs:
            logger.info(
                "fix_placeholder_emails_complete", fixed=0, not_found=0, total=0
            )
            return {"fixed": 0, "not_found": 0, "total": 0}

        sem = asyncio.Semaphore(8)

        async def _process_job(job) -> str:
            async with sem:
                try:
                    old_email = job.hr_email
                    (
                        email,
                        resolved_company,
                        resolved_website,
                    ) = await _discover_email_for_job(
                        job_id=job.id,
                        job_title=job.job_title,
                        company=job.company,
                        job_description=job.job_description,
                        company_website=job.company_website,
                        job_url=job.job_url,
                    )

                    # Only accept the result if it is a non-placeholder email
                    found_real = email is not None and not is_placeholder_email(email)

                    async with session_factory() as session:
                        db_job = await session.get(Job, job.id)
                        if db_job:
                            db_job.hr_email_discovery_attempts = (db_job.hr_email_discovery_attempts or 0) + 1

                            if found_real:
                                db_job.hr_email = email
                                db_job.hr_email_discovery_status = "found"
                                db_job.hr_email_discovered_at = _utcnow()
                                from services.api.models.hr_email_utils import upsert_hr_email as _upsert_hr_email
                                await _upsert_hr_email(
                                    session=session,
                                    tenant_id=db_job.tenant_id,
                                    email=email,
                                    increment_job_count=True,
                                )
                            else:
                                # Clear placeholder — backfill_hr_emails_task will retry
                                db_job.hr_email = None
                                db_job.hr_email_discovery_status = "not_found"

                            if resolved_company and (
                                not db_job.company
                                or db_job.company.lower() == "unknown"
                            ):
                                db_job.company = resolved_company
                            if resolved_website and not db_job.company_website:
                                db_job.company_website = resolved_website
                            await session.commit()
                        else:
                            logger.warning(
                                "fix_placeholder_job_deleted_during_update",
                                job_id=job.id,
                                email_found=bool(found_real),
                            )

                    if found_real:
                        logger.info(
                            "placeholder_email_replaced",
                            job_id=job.id,
                            company=job.company,
                            old_email=old_email,
                            new_email=email,
                        )
                        return "fixed"
                    else:
                        logger.debug(
                            "placeholder_email_cleared",
                            job_id=job.id,
                            company=resolved_company or job.company,
                        )
                        return "not_found"

                except Exception as exc:
                    log_exception(
                        logger, "fix_placeholder_job_failed", exc, job_id=job.id
                    )
                    return "not_found"
                finally:
                    await asyncio.sleep(1)

        results = await asyncio.gather(*[_process_job(j) for j in jobs])
        fixed = results.count("fixed")
        not_found = results.count("not_found")

        logger.info(
            "fix_placeholder_emails_complete",
            fixed=fixed,
            not_found=not_found,
            total=len(jobs),
        )
        return {"fixed": fixed, "not_found": not_found, "total": len(jobs)}

    return _run_async(_run())



# ------------------------------------------------------------------ #
# Weekly cleanup task                                                  #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.scraper.tasks.deduplicate_jobs_task",
)
@cron_safe(
    task_name="deduplicate_jobs_task",
    singleton_ttl_seconds=900,  # 15 min - matches cron interval
    max_runs_per_hour=4,  # Every 15 min = 4/hour
    max_queue_depth=5000,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=1800,
)
@cron_monitored("deduplicate_jobs_task")
def deduplicate_jobs_task() -> dict:
    """Every 5 min — removes duplicate jobs sharing the same (tenant_id, company).

    Keep strategy (per duplicate group):
      - Prefer the job with the most advanced status
      - Tie-break by most recent scraped_at (keep newest).
    """

    logger.info("deduplicate_jobs_started")

    async def _run():
        from sqlalchemy import text

        from services.api.core.database import get_worker_session_factory

        _status_priority = """
            CASE status
                WHEN 'sent'             THEN 0
                WHEN 'pending_approval' THEN 1
                WHEN 'cover_generated'  THEN 2
                WHEN 'scoring'          THEN 3
                WHEN 'new'              THEN 4
                WHEN 'filtered'         THEN 5
                ELSE                         6
            END
        """

        _duplicates_cte = f"""
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY tenant_id,
                                        LOWER(TRIM(company))
                           ORDER BY {_status_priority}, scraped_at DESC
                       ) AS rn
                FROM jobs
            )
            SELECT id FROM ranked WHERE rn > 1
        """

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            lock_result = await session.execute(
                text("SELECT pg_try_advisory_xact_lock(42001)")
            )
            if not lock_result.scalar():
                logger.info("deduplicate_jobs_skipped_locked")
                return {"deleted": 0, "skipped": "another_instance_running"}

            await session.execute(
                text("CREATE TEMP TABLE _dup_ids (id VARCHAR(36)) ON COMMIT DROP")
            )
            await session.execute(
                text(f"INSERT INTO _dup_ids {_duplicates_cte}")
            )

            r_count = await session.execute(
                text("SELECT COUNT(*) FROM _dup_ids")
            )
            total = r_count.scalar()

            if total == 0:
                logger.debug("deduplicate_jobs_complete", deleted=0)
                return {"deleted": 0}

            r_logs = await session.execute(
                text("DELETE FROM send_logs WHERE job_id IN (SELECT id FROM _dup_ids)")
            )
            r_emb = await session.execute(
                text("DELETE FROM embeddings WHERE job_id IN (SELECT id FROM _dup_ids)")
            )
            r_jobs = await session.execute(
                text("DELETE FROM jobs WHERE id IN (SELECT id FROM _dup_ids)")
            )

            await session.commit()

        logger.info(
            "deduplicate_jobs_complete",
            deleted=r_jobs.rowcount,
            send_logs_deleted=r_logs.rowcount,
            embeddings_deleted=r_emb.rowcount,
        )

        return {
            "deleted": r_jobs.rowcount,
            "send_logs_deleted": r_logs.rowcount,
            "embeddings_deleted": r_emb.rowcount,
        }

    return _run_async(_run())


@celery_app.task(
    name="services.scraper.tasks.cleanup_old_jobs_task",
)
@cron_safe(
    task_name="cleanup_old_jobs_task",
    singleton_ttl_seconds=86400,  # 24h - daily task
    max_runs_per_hour=1,  # Only once per day
    max_queue_depth=5000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=7200,
)
@cron_monitored("cleanup_old_jobs_task")
def cleanup_old_jobs_task() -> dict:
    """Weekly — archives jobs older than 30 days with terminal statuses.

    Deletes orphaned embeddings rows for cleaned-up jobs.
    Leaves send_logs intact (audit trail).
    Terminal statuses: sent, bounced, ignored, error.
    """
    DAYS_OLD = 30
    TERMINAL_STATUSES = ("sent", "bounced", "error")
    logger.info("cleanup_old_jobs_started", days_old=DAYS_OLD)

    async def _run():
        from sqlalchemy import text

        from services.api.core.database import get_worker_session_factory

        statuses_sql = ", ".join(f"'{s}'" for s in TERMINAL_STATUSES)
        _condition = (
            f"status IN ({statuses_sql})"
            f" AND scraped_at < NOW() - INTERVAL '{DAYS_OLD} days'"
        )

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            r_embeddings = await session.execute(
                text(
                    f"DELETE FROM embeddings WHERE job_id IN (SELECT id FROM jobs WHERE {_condition})"
                )
            )
            r_jobs = await session.execute(text(f"DELETE FROM jobs WHERE {_condition}"))
            await session.commit()

        logger.info(
            "cleanup_old_jobs_complete",
            jobs_deleted=r_jobs.rowcount,
            embeddings_deleted=r_embeddings.rowcount,
        )
        return {
            "jobs_deleted": r_jobs.rowcount,
            "embeddings_deleted": r_embeddings.rowcount,
        }

    return _run_async(_run())


@celery_app.task(
    name="services.scraper.tasks.purge_old_cron_runs_task",
)
@cron_safe(
    task_name="purge_old_cron_runs_task",
    singleton_ttl_seconds=86400,
    max_runs_per_hour=1,
    max_queue_depth=5000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=7200,
)
@cron_monitored("purge_old_cron_runs_task")
def purge_old_cron_runs_task() -> dict:
    """Nightly — deletes CronRun rows older than 30 days."""
    DAYS_OLD = 30
    logger.info("purge_old_cron_runs_started", days_old=DAYS_OLD)

    async def _run():
        from sqlalchemy import text

        from services.api.core.database import get_worker_session_factory

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            r = await session.execute(
                text(
                    f"DELETE FROM cron_runs WHERE started_at < NOW() - INTERVAL '{DAYS_OLD} days'"
                )
            )
            await session.commit()

        deleted = r.rowcount
        logger.info("purge_old_cron_runs_complete", deleted=deleted)
        return {"cron_runs_deleted": deleted}

    return _run_async(_run())


# ------------------------------------------------------------------ #
# Purge jobs with old posted_date (one-time / admin-triggered)        #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.scraper.tasks.purge_old_dated_jobs_task",
)
@cron_safe(
    task_name="purge_old_dated_jobs_task",
    singleton_ttl_seconds=3600,
    max_runs_per_hour=2,
    max_queue_depth=5000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=3600,
)
@cron_monitored("purge_old_dated_jobs_task")
def purge_old_dated_jobs_task() -> dict:
    """Delete jobs whose posted_date is older than max_job_age_days.

    Triggered manually via admin quick action to clean up historical
    old jobs that were scraped before the date filter was active.
    Only deletes jobs with status IN ('new', 'filtered') to avoid
    removing jobs already in the application pipeline.
    """
    from services.api.core.config import get_settings
    settings = get_settings()
    max_age = settings.max_job_age_days

    logger.info("purge_old_dated_jobs_started", max_age_days=max_age)

    async def _run():
        from sqlalchemy import text

        from services.api.core.database import get_worker_session_factory

        session_factory = get_worker_session_factory()
        async with session_factory() as session:
            r_embeddings = await session.execute(
                text(
                    "DELETE FROM embeddings WHERE job_id IN ("
                    "  SELECT id FROM jobs"
                    "  WHERE posted_date IS NOT NULL"
                    f"  AND posted_date < NOW() - INTERVAL '{max_age} days'"
                    "  AND status IN ('new', 'filtered')"
                    ")"
                )
            )
            r_jobs = await session.execute(
                text(
                    "DELETE FROM jobs"
                    " WHERE posted_date IS NOT NULL"
                    f" AND posted_date < NOW() - INTERVAL '{max_age} days'"
                    " AND status IN ('new', 'filtered')"
                )
            )
            await session.commit()

        logger.info(
            "purge_old_dated_jobs_complete",
            jobs_deleted=r_jobs.rowcount,
            embeddings_deleted=r_embeddings.rowcount,
            max_age_days=max_age,
        )
        return {
            "jobs_deleted": r_jobs.rowcount,
            "embeddings_deleted": r_embeddings.rowcount,
            "max_age_days": max_age,
        }

    return _run_async(_run())


# ------------------------------------------------------------------ #
# Pipeline health check (every 15 min)                                #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.scraper.tasks.pipeline_health_check_task",
)
@cron_safe(
    task_name="pipeline_health_check_task",
    singleton_ttl_seconds=900,   # 15 min - matches cron interval
    max_runs_per_hour=4,
    max_queue_depth=5000,
    circuit_failure_threshold=5,
    circuit_recovery_seconds=1800,
)
@cron_monitored("pipeline_health_check_task")
def pipeline_health_check_task() -> dict:
    """
    Every 15 min — detects and auto-fixes pipeline stalls.

    Checks:
    - Jobs stuck in 'scoring' status > 1 hour → reset to 'filtered' for retry
    - Count of send-ready jobs (cover_generated + hr_email set) — metric only
    - Jobs in 'pending_approval' > 24h → auto-approve when AUTO_SEND_ENABLED=True
    """
    logger.info("pipeline_health_check_started")

    async def _run():
        from datetime import timedelta

        from sqlalchemy import func, select, update as sa_update

        from services.api.core.config import get_settings
        from services.api.core.database import get_worker_session_factory
        from services.api.models.db import Job

        settings = get_settings()
        session_factory = get_worker_session_factory()
        fixes: dict = {}
        now = _utcnow()

        async with session_factory() as session:
            # Fix 1: Jobs stuck in 'scoring' > 1 hour → reset to 'filtered'
            r = await session.execute(
                sa_update(Job)
                .where(Job.status == "scoring")
                .where(Job.updated_at < now - timedelta(hours=1))
                .values(status="filtered")
                .execution_options(synchronize_session=False),
            )
            fixes["unstuck_scoring"] = r.rowcount

            # Fix 2: Count send-ready jobs (metric — no action taken)
            send_ready = await session.scalar(
                select(func.count()).select_from(Job).where(
                    Job.status == "cover_generated",
                    Job.hr_email.isnot(None),
                    Job.cover_letter.isnot(None),
                )
            )
            fixes["send_ready_count"] = send_ready or 0

            # Fix 3: Auto-approve pending_approval > 24h (only when AUTO_SEND_ENABLED)
            auto_approved = 0
            if getattr(settings, "auto_send_enabled", False):
                r = await session.execute(
                    sa_update(Job)
                    .where(Job.status == "pending_approval")
                    .where(Job.updated_at < now - timedelta(hours=24))
                    .values(status="approved")
                    .execution_options(synchronize_session=False),
                )
                auto_approved = r.rowcount
            fixes["auto_approved"] = auto_approved

            # Per-status counts for monitoring
            for status in ["new", "filtered", "scoring", "cover_generated", "pending_approval"]:
                count = await session.scalar(
                    select(func.count()).select_from(Job).where(Job.status == status)
                )
                fixes[f"count_{status}"] = count or 0

            await session.commit()

        logger.info("pipeline_health_check_complete", **fixes)
        return {"status": "ok", **fixes}

    return _run_async(_run())


# ------------------------------------------------------------------ #
# Stale lock reaper (every 10 min)                                    #
# ------------------------------------------------------------------ #
@celery_app.task(
    name="services.scraper.tasks.stale_lock_reaper_task",
)
@cron_safe(
    task_name="stale_lock_reaper_task",
    singleton_ttl_seconds=600,   # 10 min - matches cron interval
    max_runs_per_hour=6,
    max_queue_depth=5000,
    circuit_failure_threshold=3,
    circuit_recovery_seconds=1800,
)
@cron_monitored("stale_lock_reaper_task")
def stale_lock_reaper_task() -> dict:
    """
    Every 10 min — cleans up orphaned Redis cron locks.

    Scans cron:lock:* and cron:circuit:* keys for entries with no TTL
    (ttl == -1). These should never exist but can appear after a worker
    crash or OOM kill before the lock release ran.

    NOTE: PostgreSQL advisory locks are intentionally NOT touched here —
    they self-heal when the holding session closes, and calling
    pg_advisory_unlock from a different session is unsafe.
    """
    logger.info("stale_lock_reaper_started")

    async def _run():
        import redis.asyncio as aioredis

        from services.api.core.config import get_settings

        settings = get_settings()
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        reaped = {"redis_locks": 0, "redis_circuits": 0}

        try:
            for pattern in ("cron:lock:*", "cron:circuit:*"):
                cursor = 0
                key_type = "locks" if "lock" in pattern else "circuits"
                while True:
                    cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                    for key in keys:
                        ttl = await redis.ttl(key)
                        if ttl == -1:  # Persistent key — should not exist; delete it
                            await redis.delete(key)
                            reaped[f"redis_{key_type}"] += 1
                    if cursor == 0:
                        break
        finally:
            await redis.aclose()

        logger.info("stale_lock_reaper_complete", **reaped)
        return {"status": "ok", **reaped}

    return _run_async(_run())


# ====================================================================== #
# Consulting / IT outsourcing scrape pipeline                              #
# ====================================================================== #
# Mirror of the MNC pipeline (dispatch → fan-out → finalize). Uses a
# separate Redis lock namespace and separate Celery queues so it can run
# concurrently with the MNC scrape on shared workers.

_CONSULTING_LOCK_KEY = "consulting:scrape:lock:{tenant_id}"
_CONSULTING_PROGRESS_KEY = "consulting:scrape:progress:{tenant_id}"


@celery_app.task(
    name="services.scraper.tasks.consulting_scrape_dispatch_task",
    bind=True,
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
    acks_late=True,
)
def consulting_scrape_dispatch_task(
    self,
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    max_companies: int = 1000,
) -> dict:
    """Grab per-tenant lock and fan out one Celery task per consulting company."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
    )

    tid = tenant_id or _resolve_default_tenant_id()
    lock_key = _CONSULTING_LOCK_KEY.format(tenant_id=tid)
    progress_key = _CONSULTING_PROGRESS_KEY.format(tenant_id=tid)
    dispatch_id = self.request.id

    acquired = _run_async(_redis_set_nx(lock_key, dispatch_id, _MNC_LOCK_TTL))
    if not acquired:
        logger.info("consulting_scrape_dispatch_skipped_already_running", tenant_id=tid)
        return {"status": "already_running", "tenant_id": tid}

    from celery import chord, group
    from services.scraper.consulting_company_loader import load_active_consulting_companies

    companies = _run_async(load_active_consulting_companies(tid))
    if max_companies and max_companies < len(companies):
        companies = companies[:max_companies]

    if not companies:
        logger.warning("consulting_scrape_dispatch_no_companies", tenant_id=tid)
        _run_async(_redis_delete(lock_key))
        return {"status": "no_companies", "tenant_id": tid, "dispatch_id": dispatch_id}

    total = len(companies)
    _run_async(_redis_hset(progress_key, {
        "dispatch_id": dispatch_id,
        "candidate_id": candidate_id or "",
        "total": total,
        "done": 0,
        "saved": 0,
        "started_at": _utcnow().isoformat(),
    }))

    header = group(
        consulting_scrape_company_task.s(
            company=company,
            candidate_id=candidate_id,
            tenant_id=tid,
            dispatch_id=dispatch_id,
        )
        for company in companies
    )
    callback = consulting_scrape_finalize_task.s(
        candidate_id=candidate_id,
        tenant_id=tid,
        dispatch_id=dispatch_id,
    )
    chord(header)(callback)

    logger.info("consulting_scrape_dispatched", tenant_id=tid, dispatch_id=dispatch_id, companies=total)
    return {
        "status": "queued",
        "tenant_id": tid,
        "dispatch_id": dispatch_id,
        "companies": total,
    }


@celery_app.task(
    name="services.scraper.tasks.consulting_scrape_company_task",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    soft_time_limit=240,
    time_limit=300,
    acks_late=True,
)
def consulting_scrape_company_task(
    self,
    company: dict,
    candidate_id: str | None,
    tenant_id: str | None,
    dispatch_id: str,
) -> dict:
    """Scrape one consulting/outsourcing company, persist jobs, dispatch scoring."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
        dispatch_id=dispatch_id,
        company=company.get("name"),
    )

    from services.scraper.adapters.consulting_career import ConsultingCareerAdapter, PORTAL_NAME as _CONSULTING_PORTAL
    adapter = ConsultingCareerAdapter()
    progress_key = _CONSULTING_PROGRESS_KEY.format(tenant_id=tenant_id or "default")

    async def _run() -> dict:
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            try:
                raw_jobs = await asyncio.wait_for(
                    adapter._scrape_company(client, company),
                    timeout=180,
                )
            except asyncio.TimeoutError:
                logger.warning("consulting_company_timeout", company=company.get("name"))
                raw_jobs = []
            except Exception as exc:
                logger.warning("consulting_company_error", company=company.get("name"), error=str(exc))
                raw_jobs = []

        # Force the consulting portal tag (the underlying adapter inherits MNC routing).
        for j in raw_jobs:
            j.source_portal = _CONSULTING_PORTAL

        if not raw_jobs:
            await _redis_hincrby(progress_key, "done", 1)
            return {"company": company.get("name"), "saved": 0, "raw": 0}

        job_data_list = [
            {
                "job_title": j.job_title,
                "company": j.company,
                "location": j.location,
                "job_description": j.job_description,
                "job_url": j.job_url,
                "posted_date": j.posted_date,
                "hr_email": j.hr_email,
                "company_website": j.company_website,
                "recruiter_name": j.recruiter_name,
                "source_portal": j.source_portal,
                "dedupe_hash": j.dedupe_hash,
                "salary_min": j.salary_min,
                "salary_max": j.salary_max,
                "salary_currency": j.salary_currency,
                "job_type": j.job_type,
                "experience_required": j.experience_required,
                "raw_data": j.raw_data,
            }
            for j in raw_jobs
        ]

        saved_job_ids = await _save_jobs_batch(job_data_list, candidate_id)
        saved_count = len(saved_job_ids)

        if saved_job_ids:
            from services.ai.tasks import generate_embedding_task, score_job_task
            bp = BatchPublisher(chunk_size=50)
            for job_id in saved_job_ids:
                bp.add(generate_embedding_task.s(job_id))
                if candidate_id:
                    bp.add(score_job_task.s(job_id, candidate_id))
            bp.flush_with_stagger(base_countdown=2, stagger_seconds=0.1)

        await _redis_hincrby(progress_key, "done", 1)
        if saved_count:
            await _redis_hincrby(progress_key, "saved", saved_count)

        return {
            "company": company.get("name"),
            "saved": saved_count,
            "raw": len(raw_jobs),
        }

    try:
        return _run_async(_run())
    except SoftTimeLimitExceeded:
        logger.warning("consulting_company_task_soft_timeout", company=company.get("name"))
        _run_async(_redis_hincrby(progress_key, "done", 1))
        return {"company": company.get("name"), "saved": 0, "raw": 0, "timeout": True}
    except Exception as exc:
        log_exception(logger, "consulting_company_task_failed", exc, company=company.get("name"))
        try:
            _run_async(_redis_hincrby(progress_key, "done", 1))
        except Exception:
            pass
        return {"company": company.get("name"), "saved": 0, "raw": 0, "error": str(exc)}


@celery_app.task(
    name="services.scraper.tasks.consulting_scrape_finalize_task",
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=180,
    acks_late=True,
)
def consulting_scrape_finalize_task(
    self,
    results: list[dict],
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    dispatch_id: str | None = None,
) -> dict:
    """Aggregate per-company results, release the Redis lock."""
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        task_id=self.request.id,
        task_name=self.name,
        worker_id=self.request.hostname,
        dispatch_id=dispatch_id,
    )

    total_saved = sum(int(r.get("saved", 0) or 0) for r in (results or []))
    total_raw = sum(int(r.get("raw", 0) or 0) for r in (results or []))
    companies = len(results or [])
    timeouts = sum(1 for r in (results or []) if r.get("timeout"))
    errors = sum(1 for r in (results or []) if r.get("error"))

    tid = tenant_id or _resolve_default_tenant_id()
    lock_key = _CONSULTING_LOCK_KEY.format(tenant_id=tid)
    progress_key = _CONSULTING_PROGRESS_KEY.format(tenant_id=tid)

    async def _finalize() -> None:
        await _redis_hset(progress_key, {
            "finished_at": _utcnow().isoformat(),
            "final_saved": total_saved,
            "final_raw": total_raw,
            "final_companies": companies,
            "final_timeouts": timeouts,
            "final_errors": errors,
        }, ttl=600)
        await _redis_delete(lock_key)

    try:
        _run_async(_finalize())
    except Exception as exc:
        log_exception(logger, "consulting_scrape_finalize_redis_error", exc)

    logger.info(
        "consulting_scrape_finalize",
        tenant_id=tid,
        dispatch_id=dispatch_id,
        companies=companies,
        saved=total_saved,
        raw=total_raw,
        timeouts=timeouts,
        errors=errors,
    )
    return {
        "portal": "consulting_direct",
        "tenant_id": tid,
        "dispatch_id": dispatch_id,
        "companies": companies,
        "saved": total_saved,
        "raw": total_raw,
        "timeouts": timeouts,
        "errors": errors,
    }


@celery_app.task(
    name="services.scraper.tasks.scrape_consulting_jobs_task",
    bind=True,
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
)
def scrape_consulting_jobs_task(
    self,
    candidate_id: str | None = None,
    tenant_id: str | None = None,
    max_companies: int = 1000,
) -> dict:
    """Legacy/standalone entry point — kicks off the consulting dispatch task."""
    res = consulting_scrape_dispatch_task.apply_async(
        kwargs={
            "candidate_id": candidate_id,
            "tenant_id": tenant_id,
            "max_companies": max_companies,
        },
        queue="jh_scraping_consulting_dispatch",
    )
    return {"status": "dispatched", "dispatch_task_id": res.id}
