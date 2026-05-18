"""Resume parsing via pypdf + LangChain structured output.

Called once during candidate onboarding to extract structured data
from a PDF resume.
"""

import structlog

from services.ai.langchain_adapter import get_structured_llm
from services.ai.schemas import ResumeData

logger = structlog.get_logger(__name__)

_RESUME_PROMPT = """\
Extract structured information from the following resume text.

Resume:
{resume_text}

Extract:
- All technical and soft skills
- Total years of professional experience (integer)
- Technologies used (programming languages, frameworks, databases, tools)
- Highest level of education and field of study
- A 1–2 sentence professional summary

Focus on PHP, Laravel, and related backend technologies if present.
"""


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF file using pypdf."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


async def parse_resume(pdf_bytes: bytes) -> ResumeData:
    """Parse a PDF resume and return structured candidate data.

    Token budget: ~1 000 tokens total.
    Falls back to empty ResumeData on any error.
    """
    try:
        text = extract_text_from_pdf(pdf_bytes)
        if not text.strip():
            logger.warning("resume_text_empty")
            return _empty_resume_data()

        # Truncate to ~2 000 chars (~500 tokens) to stay within budget
        excerpt = text[:2000]
        prompt = _RESUME_PROMPT.format(resume_text=excerpt)

        llm = get_structured_llm(ResumeData, max_tokens=400)
        result: ResumeData = await llm.ainvoke(prompt)
        logger.info(
            "resume_parsed",
            skills_count=len(result.skills),
            years=result.years_experience,
        )
        return result
    except Exception as exc:
        logger.warning("resume_parse_failed", error=str(exc))
        return _empty_resume_data()


def _empty_resume_data() -> ResumeData:
    return ResumeData(
        skills=[],
        years_experience=0,
        technologies=[],
        education="Not specified",
        summary="Resume parsing unavailable.",
    )
