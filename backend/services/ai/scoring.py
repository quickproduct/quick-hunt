"""Job relevance scoring via LangChain structured output.

Uses Groq LLM to score a job against a candidate profile and return a
structured JobRelevanceScore.  Falls back to a neutral score of 50 on any
LLM error so the pipeline never stalls.

Every call is traced in Langfuse when observability is enabled.
Pass `callbacks` explicitly when calling from within a LangGraph workflow
so the span is nested under the workflow's parent trace.
"""
from __future__ import annotations

from typing import Any

import structlog

from services.ai.langchain_adapter import get_structured_llm
from services.ai.schemas import JobRelevanceScore

logger = structlog.get_logger(__name__)

# ── Rule-based pre-filter ─────────────────────────────────────────────────────
# Applied BEFORE the LLM call. Any job matching a negative pattern is returned
# immediately with overall_score=0, saving one Groq API call (~500 tokens).

# Jobs whose titles clearly indicate a non-PHP/Laravel stack get pre-filtered.
# Patterns are matched case-insensitively on the job title.
_TITLE_NEGATIVE_PATTERNS: tuple[str, ...] = (
    "java developer", "java engineer", "java architect",
    ".net developer", ".net engineer", "c# developer", "c# engineer",
    "ruby developer", "ruby on rails", "rails developer",
    "golang developer", "go developer", "go engineer",
    "rust developer", "rust engineer",
    "android developer", "ios developer", "swift developer", "kotlin developer",
    "react native developer",
    "data scientist", "data engineer", "machine learning engineer", "ml engineer",
    "devops engineer", "sre engineer", "site reliability",
    "blockchain developer", "solidity developer",
    "embedded software", "firmware engineer",
    "cobol developer", "mainframe developer",
    "sap developer", "abap developer",
)

# Positive signals in title → always proceed to LLM (skip negative check)
_TITLE_POSITIVE_PATTERNS: tuple[str, ...] = (
    "php", "laravel", "codeigniter", "symfony", "wordpress", "magento",
    "full stack", "fullstack", "backend developer", "web developer",
    "software engineer", "software developer",  # generic — let LLM decide
)


def _rule_based_filter(job_title: str, job_description: str) -> JobRelevanceScore | None:
    """Apply fast keyword rules before the LLM call.

    Returns a zero-score JobRelevanceScore if the job is clearly irrelevant,
    or None if the job should proceed to LLM scoring.
    """
    title_lower = (job_title or "").lower()
    desc_lower = (job_description or "").lower()[:2000]

    # If the title contains a positive PHP/Laravel signal, always proceed.
    for pos in _TITLE_POSITIVE_PATTERNS:
        if pos in title_lower:
            return None

    # If the title matches a clearly non-PHP stack, reject immediately.
    for neg in _TITLE_NEGATIVE_PATTERNS:
        if neg in title_lower:
            logger.info(
                "job_pre_filtered",
                job_title=job_title,
                matched_pattern=neg,
            )
            return JobRelevanceScore(
                overall_score=0,
                skills_match=0,
                experience_match=0,
                location_match=0,
                role_alignment=0,
                is_php_laravel=False,
                detected_role_type=neg,
                reasoning=f"Pre-filtered: title pattern '{neg}' is not a PHP/Laravel role.",
            )

    # If neither PHP/Laravel nor a clear negative is in the title, check
    # the description for at least one PHP/Laravel keyword. If absent, filter.
    php_signals = ("php", "laravel", "codeigniter", "symfony", "wordpress", "magento", "yii", "cakephp")
    if not any(sig in desc_lower for sig in php_signals):
        logger.info("job_pre_filtered_no_php_in_desc", job_title=job_title)
        return JobRelevanceScore(
            overall_score=5,
            skills_match=0,
            experience_match=50,
            location_match=50,
            role_alignment=0,
            is_php_laravel=False,
            detected_role_type="non-php",
            reasoning="Pre-filtered: no PHP/Laravel keywords found in job description.",
        )

    return None  # inconclusive — let LLM decide


_SCORING_PROMPT = """\
You are an expert recruiter evaluating job-candidate fit for PHP/Laravel roles.

Job Title: {job_title}
Company: {company}
Job Description:
{job_description}

Candidate Profile:
- Skills: {skills}
- Years of experience: {years_experience}
- Bio: {bio}

Score this job against the candidate on a scale of 0–100.
Focus on PHP/Laravel suitability as the primary criterion.
If the job does not require PHP or Laravel as the PRIMARY tech stack, set is_php_laravel=false
and overall_score below 40.
"""


async def score_job_relevance(
    job_title: str,
    job_description: str,
    company: str = "",
    candidate_skills: list[str] | None = None,
    candidate_experience: int = 0,
    candidate_bio: str = "",
    callbacks: list[Any] | None = None,
) -> JobRelevanceScore:
    """Score a single job for PHP/Laravel relevance.

    Token budget: ~350 input + ~150 output ≈ 500 total.
    Falls back to overall_score=50 on LLM error.

    Args:
        callbacks: LangChain callbacks (e.g. LangfuseCallbackHandler).
                   When None a new Langfuse trace is auto-created if enabled.
    """
    # ── Fast rule-based pre-filter (no LLM call) ─────────────────────────────
    pre_filtered = _rule_based_filter(job_title, job_description)
    if pre_filtered is not None:
        return pre_filtered

    skills_str = ", ".join(candidate_skills or []) or "Not specified"
    description_excerpt = (job_description or "")[:1500]  # cap to ~400 tokens

    prompt = _SCORING_PROMPT.format(
        job_title=job_title,
        company=company or "Unknown",
        job_description=description_excerpt,
        skills=skills_str,
        years_experience=candidate_experience,
        bio=candidate_bio or "Not provided",
    )

    # Auto-create a Langfuse trace when no callbacks are passed from a parent context
    _callbacks = callbacks
    if _callbacks is None:
        from services.ai.observability import get_callback_handler
        handler = get_callback_handler(
            "job_scoring",
            tags=["scoring", "langchain"],
            metadata={"job_title": job_title, "company": company},
        )
        _callbacks = [handler] if handler else []

    try:
        from services.ai.rate_limiter import get_least_used_key, wait_for_groq_slot
        key_id = await get_least_used_key()
        slot_ok = await wait_for_groq_slot(key_id)
        if not slot_ok:
            logger.warning("scoring_rate_limit_timeout", job_title=job_title)

        llm = get_structured_llm(JobRelevanceScore, max_tokens=200, callbacks=_callbacks)
        result: JobRelevanceScore = await llm.ainvoke(prompt)
        logger.info(
            "job_scored",
            job_title=job_title,
            score=result.overall_score,
            is_php_laravel=result.is_php_laravel,
        )
        return result
    except Exception as exc:
        logger.warning("job_scoring_failed", job_title=job_title, error=str(exc))
        return JobRelevanceScore(
            overall_score=50,
            skills_match=50,
            experience_match=50,
            location_match=50,
            role_alignment=50,
            is_php_laravel=True,
            detected_role_type="unknown",
            reasoning="Scoring unavailable — LLM call failed.",
        )
