"""LangChain-powered cover letter generation.

Falls back to the existing hardcoded template on any LLM error so the
pipeline is always resilient.

Every call is traced in Langfuse when observability is enabled.
Pass `callbacks` explicitly when calling from within a LangGraph workflow
(the workflow's parent trace callbacks are forwarded) so all spans appear
under the same workflow trace.  Leave `callbacks=None` for standalone calls —
a new Langfuse trace is created automatically.
"""
from __future__ import annotations

from typing import Any

import structlog

from services.ai.langchain_adapter import get_structured_llm
from services.ai.schemas import CoverLetterOutput

logger = structlog.get_logger(__name__)

_COVER_LETTER_PROMPT = """\
You are a professional job application writer specialising in PHP/Laravel roles.

Write a compelling cover letter for the following job application.

Job Title: {job_title}
Company: {company}
Job Description:
{job_description}

Candidate:
- Name: {candidate_name}
- Skills: {skills}
- Bio: {bio}

Tone: {tone}

Guidelines:
- Keep the full letter under 300 words.
- Opening paragraph: express genuine interest in the role and company.
- Body paragraphs: highlight 2–3 specific PHP/Laravel achievements or skills.
- Closing: clear call to action.
- Do NOT include a date, address header, or any closing signature
  ("Sincerely", "Best regards", "Regards", etc.) — these are added
  automatically by the email template. End your letter after the closing
  sentence of the final paragraph.
"""


async def generate_cover_letter_langchain(
    job_title: str,
    company: str,
    job_description: str,
    candidate_name: str,
    candidate_skills: list[str] | None = None,
    candidate_bio: str = "",
    tone: str = "professional",
    callbacks: list[Any] | None = None,
) -> CoverLetterOutput:
    """Generate a structured cover letter via LangChain.

    Token budget: ~600 input + ~400 output ≈ 1 000 total.
    Falls back to a simple plain-text template on failure.

    Args:
        callbacks: LangChain callbacks (e.g. LangfuseCallbackHandler).
                   When None a new Langfuse trace is auto-created if enabled.
    """
    skills_str = ", ".join(candidate_skills or []) or "PHP, Laravel"
    description_excerpt = (job_description or "")[:1200]

    prompt = _COVER_LETTER_PROMPT.format(
        job_title=job_title,
        company=company or "your company",
        job_description=description_excerpt,
        candidate_name=candidate_name,
        skills=skills_str,
        bio=candidate_bio or "Experienced PHP/Laravel developer.",
        tone=tone,
    )

    # Auto-create a Langfuse trace when no callbacks are passed from a parent context
    _callbacks = callbacks
    if _callbacks is None:
        from services.ai.observability import get_callback_handler
        handler = get_callback_handler(
            "cover_letter_generation",
            tags=["cover_letter", "langchain"],
            metadata={
                "job_title": job_title,
                "company": company,
                "candidate": candidate_name,
                "tone": tone,
            },
        )
        _callbacks = [handler] if handler else []

    try:
        from services.ai.rate_limiter import get_least_used_key, wait_for_groq_slot
        key_id = await get_least_used_key()
        slot_ok = await wait_for_groq_slot(key_id)
        if not slot_ok:
            logger.warning("cover_letter_rate_limit_timeout", job_title=job_title)

        llm = get_structured_llm(CoverLetterOutput, max_tokens=600, callbacks=_callbacks)
        result: CoverLetterOutput = await llm.ainvoke(prompt)
        logger.info("cover_letter_generated_langchain", job_title=job_title, company=company)
        return result
    except Exception as exc:
        logger.warning(
            "cover_letter_langchain_failed",
            job_title=job_title,
            error=str(exc),
        )
        return _fallback_cover_letter(job_title, company, candidate_name, skills_str)


def _fallback_cover_letter(
    job_title: str,
    company: str,
    candidate_name: str,
    skills_str: str,
) -> CoverLetterOutput:
    """Simple template-based fallback used when the LLM call fails."""
    opening = (
        f"I am writing to express my strong interest in the {job_title} position at {company}. "
        "With my background in PHP and Laravel development, I am confident I can contribute "
        "meaningfully to your team."
    )
    body = [
        f"My technical expertise includes {skills_str}. "
        "I have delivered scalable, maintainable web applications using these technologies "
        "and follow best practices such as SOLID principles and test-driven development.",
        "I thrive in collaborative environments and take pride in clean, well-documented code. "
        "I am always eager to learn and adapt to new challenges.",
    ]
    closing = (
        f"I would welcome the opportunity to discuss how my skills align with {company}'s needs. "
        "Please find my resume attached. Thank you for your time and consideration."
    )
    full_text = "\n\n".join([opening] + body + [closing])
    return CoverLetterOutput(
        subject_line=f"Application for {job_title} at {company}",
        opening_paragraph=opening,
        body_paragraphs=body,
        closing_paragraph=closing,
        full_text=full_text,
    )
