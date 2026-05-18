"""All Pydantic v2 request/response schemas."""
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ------------------------------------------------------------------ #
# Candidate schemas                                                    #
# ------------------------------------------------------------------ #
class CandidateCreate(BaseModel):
    name: str
    email: str
    skills: list[str] = []
    years_experience: Optional[int] = None
    resume_url: Optional[str] = None
    target_roles: list[str] = []
    target_locations: list[str] = []
    bio: Optional[str] = None
    cover_letter_template: Optional[str] = None
    static_cover_letter: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None


class CandidateUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    skills: Optional[list[str]] = None
    years_experience: Optional[int] = None
    resume_url: Optional[str] = None
    target_roles: Optional[list[str]] = None
    target_locations: Optional[list[str]] = None
    bio: Optional[str] = None
    cover_letter_template: Optional[str] = None
    static_cover_letter: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    is_active: Optional[bool] = None


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    skills: list[str] = []
    years_experience: Optional[int] = None
    resume_url: Optional[str] = None
    target_roles: list[str] = []
    target_locations: list[str] = []
    bio: Optional[str] = None
    cover_letter_template: Optional[str] = None
    static_cover_letter: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ------------------------------------------------------------------ #
# Job schemas                                                          #
# ------------------------------------------------------------------ #
class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: Optional[str] = None
    job_title: str
    company: str
    location: Optional[str] = None
    job_description: Optional[str] = None
    job_url: str
    posted_date: Optional[datetime] = None
    scraped_at: Optional[datetime] = None
    hr_email: Optional[str] = None
    company_website: Optional[str] = None
    recruiter_name: Optional[str] = None
    source_portal: str
    status: str
    dedupe_hash: str
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    job_type: Optional[str] = None
    experience_required: Optional[str] = None
    relevance_score: Optional[float] = None
    score_breakdown: Optional[dict] = None
    cover_letter: Optional[str] = None
    cover_letter_generated_at: Optional[datetime] = None


class JobStatusUpdate(BaseModel):
    status: str = Field(
        ...,
        pattern=(
            "^(new|filtered|scoring|cover_generated"
            "|pending_approval|sending|sent|bounced|error)$"
        ),
    )


class GenerateCoverRequest(BaseModel):
    candidate_id: str
    tone: str = "professional"
    custom_instructions: str = ""


# ------------------------------------------------------------------ #
# Search schemas                                                       #
# ------------------------------------------------------------------ #
class SearchRequest(BaseModel):
    job_titles: list[str] = Field(..., min_length=1)
    locations: list[str] = ["India"]
    portals: list[str] = ["naukri", "indeed"]
    max_results_per_portal: int = Field(default=50, ge=1, le=500)
    candidate_id: str
    auto_generate_covers: bool = False
    auto_send: bool = False


class SearchResponse(BaseModel):
    task_id: str
    celery_task_ids: list[str]
    message: str
    portals: list[str]
    estimated_jobs: int


class SearchTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    candidate_id: str
    job_titles: list[str] = []
    locations: list[str] = []
    portals: list[str] = []
    max_results_per_portal: int
    celery_task_id: Optional[str] = None
    status: str
    jobs_found: int
    jobs_old_skipped: int = 0
    jobs_date_unavailable: int = 0
    tasks_total: int = 0
    tasks_completed: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None


# ------------------------------------------------------------------ #
# Send schemas                                                         #
# ------------------------------------------------------------------ #
class HrEmailUpdate(BaseModel):
    hr_email: str


class SendRequest(BaseModel):
    candidate_id: str
    override_email: Optional[str] = None
    override_subject: Optional[str] = None
    attach_resume: bool = True
    dry_run: bool = False


class BulkGenerateCoverRequest(BaseModel):
    job_ids: list[str] = Field(..., min_length=1, max_length=100)
    candidate_id: str
    tone: str = "professional"
    custom_instructions: str = ""


class SkippedJob(BaseModel):
    job_id: str
    reason: str  # "no_hr_email" | "no_cover_letter" | "already_sent" | "not_found"


class BulkSendRequest(BaseModel):
    job_ids: list[str] = Field(..., min_length=1, max_length=100)
    candidate_id: str
    attach_resume: bool = True
    dry_run: bool = False


class BulkSendResponse(BaseModel):
    queued: int
    skipped: list[SkippedJob]
    task_ids: list[str]
    dry_run: bool


class SendLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    candidate_id: str
    to_email: str
    subject: Optional[str] = None
    body_snippet: Optional[str] = None
    status: str
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class SendLogEnrichedOut(SendLogOut):
    """SendLogOut enriched with job title and company from the related Job."""
    job_title: Optional[str] = None
    company: Optional[str] = None


# ------------------------------------------------------------------ #
# Stats schema                                                         #
# ------------------------------------------------------------------ #
class StatsOut(BaseModel):
    total_jobs: int
    jobs_by_status: dict[str, int]
    jobs_by_portal: dict[str, int]
    emails_sent: int
    emails_delivered: int
    emails_opened: int
    emails_clicked: int
    emails_bounced: int = 0
    emails_soft_bounced: int = 0
    cover_letters_generated: int
    jobs_with_hr_email: int
    jobs_ready: int = 0  # jobs with both cover letter + valid (non-placeholder) HR email
    jobs_missing_hr: int = 0   # scraped but HR email not found yet
    jobs_pending_approval: int = 0  # cover generated, awaiting manual approval
    jobs_hr_unreachable: int = 0  # HR email discovery exhausted (max attempts reached)


# ------------------------------------------------------------------ #
# HR Email Pipeline Health                                             #
# ------------------------------------------------------------------ #
class HREmailPipelineStats(BaseModel):
    """Health check for the HR email discovery pipeline."""
    # Counts by discovery status
    jobs_pending_discovery: int = 0      # hr_email IS NULL, attempts < max
    jobs_unreachable: int = 0            # hr_email IS NULL, attempts >= max
    jobs_found: int = 0                  # hr_email IS NOT NULL
    # Cover-ready bottleneck
    cover_ready_missing_hr: int = 0      # status=cover_generated, hr_email IS NULL
    cover_ready_with_hr: int = 0         # status=cover_generated, hr_email IS NOT NULL
    # Breakdown by discovery status
    discovery_status_counts: dict[str, int] = {}
    # Breakdown by portal for cover_ready missing HR
    missing_hr_by_portal: dict[str, int] = {}
    # Circuit breaker state (from Redis)
    circuit_breakers: dict[str, str] = {}  # task_name -> state (open/closed/half_open)


# ------------------------------------------------------------------ #
# Blacklist schemas                                                    #
# ------------------------------------------------------------------ #
class BlacklistedCompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    reason: Optional[str] = Field(default=None, max_length=500)


class BlacklistedCompanyUpdate(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class BlacklistedCompanyOut(BaseModel):
    id: str
    name: str
    reason: Optional[str]
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class TimelineEvent(BaseModel):
    """Single lifecycle event in a job's application timeline."""
    event: str          # scraped | scored | cover_generated | email_sent | delivered | opened | clicked
    label: str          # Human-readable label
    timestamp: Optional[datetime]
    done: bool          # Whether this step has occurred
    metadata: Optional[dict] = None  # Extra context (score, email, etc.)


class JobTimeline(BaseModel):
    job_id: str
    events: list[TimelineEvent]
