"""Pydantic output models for LangChain structured outputs."""

from pydantic import BaseModel, Field


class JobRelevanceScore(BaseModel):
    """Structured output for job relevance scoring."""

    overall_score: int = Field(ge=0, le=100, description="0–100 overall relevance score")
    skills_match: int = Field(ge=0, le=100, description="How well candidate skills match")
    experience_match: int = Field(ge=0, le=100, description="Experience level alignment")
    location_match: int = Field(ge=0, le=100, description="Location preference match")
    role_alignment: int = Field(ge=0, le=100, description="Role type alignment with PHP/Laravel")
    is_php_laravel: bool = Field(description="True if job is genuinely PHP/Laravel-focused")
    detected_role_type: str = Field(
        description='e.g. "php developer" | "laravel developer" | "full stack php"'
    )
    reasoning: str = Field(description="1–2 sentence explanation of the score")


class CoverLetterOutput(BaseModel):
    """Structured output for cover letter generation."""

    subject_line: str = Field(description="Email subject line for the application")
    opening_paragraph: str = Field(description="Opening paragraph of the cover letter")
    body_paragraphs: list[str] = Field(description="2–3 body paragraphs")
    closing_paragraph: str = Field(description="Closing paragraph with call to action")
    full_text: str = Field(description="Complete cover letter text (all sections combined)")


class PersonalizedEmail(BaseModel):
    """Structured output for personalised HR email."""

    subject: str = Field(description="Email subject line")
    greeting: str = Field(description='e.g. "Dear {name}," or "Hi {name},"')
    opening_line: str = Field(description="Company-specific hook for the first sentence")


class ResumeData(BaseModel):
    """Structured output for resume parsing."""

    skills: list[str] = Field(description="Technical and soft skills")
    years_experience: int = Field(ge=0, description="Total years of professional experience")
    technologies: list[str] = Field(description="Technologies used, e.g. PHP, Laravel, MySQL")
    education: str = Field(description="Highest education level and field")
    summary: str = Field(description="1–2 sentence professional summary")


class PHPLaravelRelevance(BaseModel):
    """Semantic filter output — is this job genuinely PHP/Laravel focused?"""

    is_relevant: bool = Field(description="True if job requires PHP/Laravel as primary stack")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score")
    reason: str = Field(description="Brief explanation")
