"""LangGraph application workflow.

Flow:
  START → AnalyzeJob → ScoreJob → RouteByScore
    ├─ score >= threshold (PHP/Python) → GenerateCoverLetter → RequireApproval
    │     ├─ auto_send=True (or approval received) → SendApplication → END
    │     └─ requires approval          → [interrupt, job.status=pending_approval]
    ├─ non-PHP/Python job               → StaticCoverLetter → END
    │     (cover_generated, waits for HR email discovery to make it send-ready)
    └─ score < threshold (PHP/Python)   → DiscardJob → END

Celery executes work (HTTP, DB writes, email sends).
LangGraph controls the flow logic and stores checkpoints in Redis.
Thread ID = job_id (unique per application).

Checkpointing:
  Uses langgraph.checkpoint.redis.RedisSaver backed by the existing
  Upstash Redis URL.  Checkpoint TTL is 24 h — enough for human approval.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import structlog
from langchain_core.runnables import RunnableConfig
from typing_extensions import TypedDict

logger = structlog.get_logger(__name__)

SCORE_THRESHOLD = int(os.environ.get("SCORE_THRESHOLD", "60"))


# ── Workflow state ─────────────────────────────────────────────────────────────

class ApplicationWorkflowState(TypedDict):
    job_id: str
    candidate_id: str
    job_data: dict           # raw job fields from DB
    candidate_data: dict     # candidate fields from DB
    job_analysis: Optional[dict]       # from analyze_job_node
    relevance_score: Optional[dict]    # serialised JobRelevanceScore
    cover_letter: Optional[str]        # generated cover letter text
    approval_status: str               # "auto" | "pending" | "approved" | "rejected"
    send_result: Optional[dict]
    error: Optional[str]


# ── Node implementations ───────────────────────────────────────────────────────

async def analyze_job_node(state: ApplicationWorkflowState) -> dict:
    """Extract role type and tech stack from the job description."""
    job = state["job_data"]
    title = job.get("job_title", "")
    desc = (job.get("job_description") or "")[:500]
    # Light analysis without an extra LLM call — derive from keywords
    is_php = any(kw in (title + " " + desc).lower() for kw in ("php", "laravel"))
    analysis = {
        "role_type": title.lower(),
        "is_php_stack": is_php,
        "tech_hints": [kw for kw in ("php", "laravel", "mysql", "redis") if kw in desc.lower()],
    }
    logger.debug("analyze_job_node_complete", job_id=state["job_id"], analysis=analysis)
    return {"job_analysis": analysis}


async def score_job_node(state: ApplicationWorkflowState, config: RunnableConfig) -> dict:
    """Call LangChain scoring and store result in state.

    Non-PHP/Python jobs skip the LLM scorer entirely — they always route to
    static_cover regardless of score, so the API call would be wasted.
    """
    from services.ai.scoring import score_job_relevance

    job = state["job_data"]
    candidate = state["candidate_data"]

    # Skip LLM scoring for non-PHP/Python jobs — route_by_score will send
    # them to static_cover based on is_php_laravel=False.
    if not job.get("is_php_python", True):
        logger.info("score_job_node_skipped_non_php", job_id=state["job_id"])
        score_data = {
            "overall_score": 50,
            "is_php_laravel": False,
            "detected_role_type": "non_php_python",
            "reasoning": "Non-PHP/Python — static cover letter path",
        }
        await _persist_static_score(state["job_id"], score_data)
        return {"relevance_score": score_data}

    # Forward workflow-level callbacks so scoring spans are nested under the
    # parent application_workflow trace in Langfuse.
    callbacks = (config or {}).get("callbacks") or None

    score = await score_job_relevance(
        job_title=job.get("job_title", ""),
        job_description=job.get("job_description") or "",
        company=job.get("company", ""),
        candidate_skills=candidate.get("skills") or [],
        candidate_experience=candidate.get("years_experience") or 0,
        candidate_bio=candidate.get("bio") or "",
        callbacks=callbacks,
    )

    # Persist score to DB immediately so the dashboard shows it
    await _update_job_score(state["job_id"], score)

    logger.info(
        "score_job_node_complete",
        job_id=state["job_id"],
        score=score.overall_score,
        is_php=score.is_php_laravel,
    )
    return {"relevance_score": score.model_dump()}


def route_by_score(state: ApplicationWorkflowState) -> str:
    """Conditional edge: proceed, use static cover, or discard based on score."""
    score_data = state.get("relevance_score") or {}
    overall = score_data.get("overall_score", 0)
    is_php = score_data.get("is_php_laravel", True)

    if not is_php:
        return "static_cover"
    if overall < SCORE_THRESHOLD:
        return "discard"
    return "generate"


async def generate_cover_node(state: ApplicationWorkflowState, config: RunnableConfig) -> dict:
    """Generate cover letter via LangChain."""
    from services.ai.cover_letter import generate_cover_letter_langchain

    job = state["job_data"]
    candidate = state["candidate_data"]

    # Forward workflow-level callbacks so cover letter spans are nested under
    # the parent application_workflow trace in Langfuse.
    callbacks = (config or {}).get("callbacks") or None

    result = await generate_cover_letter_langchain(
        job_title=job.get("job_title", ""),
        company=job.get("company", ""),
        job_description=job.get("job_description") or "",
        candidate_name=candidate.get("name", ""),
        candidate_skills=candidate.get("skills") or [],
        candidate_bio=candidate.get("bio") or "",
        callbacks=callbacks,
    )

    # Save generated cover letter to DB
    await _update_job_cover_letter(state["job_id"], result.full_text)

    logger.info("generate_cover_node_complete", job_id=state["job_id"])
    return {"cover_letter": result.full_text}


async def require_approval_node(state: ApplicationWorkflowState) -> dict:
    """If candidate requires manual approval, set status=pending_approval and interrupt."""
    from services.api.core.config import get_settings

    # When auto-send is globally disabled, always require manual approval
    if not get_settings().auto_send_enabled:
        await _set_job_status(state["job_id"], "pending_approval")
        logger.info("require_approval_node_auto_send_disabled", job_id=state["job_id"])
        return {"approval_status": "pending"}

    candidate = state["candidate_data"]
    auto_send = candidate.get("auto_send", False)

    if auto_send or state.get("approval_status") == "approved":
        return {"approval_status": "auto"}

    # Mark job as pending approval in DB so the dashboard shows it
    await _set_job_status(state["job_id"], "pending_approval")
    logger.info("require_approval_node_interrupted", job_id=state["job_id"])
    return {"approval_status": "pending"}


def route_by_approval(state: ApplicationWorkflowState) -> str:
    """Conditional edge after approval check."""
    status = state.get("approval_status", "pending")
    if status in ("auto", "approved"):
        return "send"
    return "wait"  # workflow is interrupted here


async def send_application_node(state: ApplicationWorkflowState) -> dict:
    """Dispatch the Celery email send task — skips if an active send already exists."""
    from sqlalchemy import select
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import SendLog
    from services.sender.tasks import send_application_email_task, _ACTIVE_SEND_STATUSES

    job_id = state["job_id"]
    candidate_id = state["candidate_id"]

    # Guard: don't dispatch if an active/in-flight send_log already exists.
    # The workflow can run again (e.g. after re-approval), so this prevents
    # double-sends when the workflow re-enters the send node.
    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        existing = await session.execute(
            select(SendLog.id).where(
                SendLog.job_id == job_id,
                SendLog.candidate_id == candidate_id,
                SendLog.status.in_(_ACTIVE_SEND_STATUSES),
            ).limit(1)
        )
        if existing.first():
            logger.info("send_application_node_skipped_duplicate", job_id=job_id)
            return {"send_result": {"skipped": "duplicate_active_send"}}

    await _set_job_status(job_id, "sending")

    task = send_application_email_task.apply_async(
        args=[job_id, candidate_id],
        countdown=5,
    )

    logger.info("send_application_node_dispatched", job_id=job_id, celery_id=task.id)
    return {"send_result": {"celery_task_id": task.id}}


async def static_cover_letter_node(state: ApplicationWorkflowState) -> dict:
    """Assign static cover letter for non-PHP/Python jobs.

    Finds the active candidate, writes their static_cover_letter to the job,
    and sets status='cover_generated'. The job then sits ready until
    backfill_hr_emails_task discovers an HR email, at which point it becomes
    send-ready for manual or auto dispatch.
    """
    from sqlalchemy import select
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Candidate, Job

    job_id = state["job_id"]
    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        candidate_id = state.get("candidate_id")
        candidate = await session.get(Candidate, candidate_id) if candidate_id else None
        if not candidate:
            result = await session.execute(
                select(Candidate).where(Candidate.is_active.is_(True)).limit(1)
            )
            candidate = result.scalar_one_or_none()

        if not candidate:
            logger.warning("static_cover_letter_node_no_candidate", job_id=job_id)
            await _set_job_status(job_id, "filtered")
            return {"approval_status": "rejected"}

        cover_text = candidate.static_cover_letter or candidate.cover_letter_template or ""
        if not cover_text:
            logger.warning("static_cover_letter_node_no_cover", job_id=job_id, candidate_id=candidate.id)
            await _set_job_status(job_id, "filtered")
            return {"approval_status": "rejected"}

        from datetime import datetime, timezone
        from sqlalchemy import update
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                candidate_id=candidate.id,
                cover_letter=cover_text,
                cover_letter_generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="cover_generated",
            )
        )
        await session.commit()

    logger.info(
        "static_cover_letter_node_complete",
        job_id=job_id,
        candidate_id=candidate.id,
        cover_source="static" if candidate.static_cover_letter else "template",
    )
    return {"cover_letter": cover_text, "approval_status": "pending"}


async def discard_job_node(state: ApplicationWorkflowState) -> dict:
    """Mark job as filtered/discarded — score too low (PHP/Python jobs only)."""
    await _set_job_status(state["job_id"], "filtered")
    logger.info(
        "discard_job_node_complete",
        job_id=state["job_id"],
        score=state.get("relevance_score", {}).get("overall_score"),
    )
    # LangGraph requires every node to write at least one state field.
    return {"approval_status": "rejected"}


# ── DB helpers ─────────────────────────────────────────────────────────────────

async def _update_job_score(job_id: str, score) -> None:
    from sqlalchemy import update
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                relevance_score=float(score.overall_score),
                score_breakdown=score.model_dump(),
                status="scoring",
            )
        )
        await session.commit()


async def _update_job_cover_letter(job_id: str, cover_text: str) -> None:
    from datetime import datetime, timezone
    from sqlalchemy import update
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                cover_letter=cover_text,
                cover_letter_generated_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="cover_generated",
            )
        )
        await session.commit()


async def _persist_static_score(job_id: str, score_data: dict) -> None:
    """Write a synthetic score record to DB for non-PHP/Python jobs.

    These jobs skip LLM scoring but still need a DB score so the Application
    Timeline displays correctly instead of showing a stale LLM value.
    """
    from sqlalchemy import update
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(
                relevance_score=float(score_data["overall_score"]),
                score_breakdown=score_data,
                status="scoring",
            )
        )
        await session.commit()


async def _set_job_status(job_id: str, status: str) -> None:
    from sqlalchemy import update
    from services.api.core.database import get_worker_session_factory
    from services.api.models.db import Job

    session_factory = get_worker_session_factory()
    async with session_factory() as session:
        await session.execute(
            update(Job).where(Job.id == job_id).values(status=status)
        )
        await session.commit()


# ── Graph builder ──────────────────────────────────────────────────────────────

def build_workflow(use_checkpointing: bool = True):
    """Compile the LangGraph application workflow.

    Returns a CompiledGraph ready for ainvoke() / astream().
    Checkpointing stores state in Redis with TTL=24 h.
    Pass use_checkpointing=False in unit tests.
    """
    from langgraph.graph import END, StateGraph

    graph = StateGraph(ApplicationWorkflowState)

    # Nodes
    graph.add_node("analyze_job", analyze_job_node)
    graph.add_node("score_job", score_job_node)
    graph.add_node("generate_cover", generate_cover_node)
    graph.add_node("static_cover", static_cover_letter_node)
    graph.add_node("require_approval", require_approval_node)
    graph.add_node("send_application", send_application_node)
    graph.add_node("discard_job", discard_job_node)

    # Edges
    graph.set_entry_point("analyze_job")
    graph.add_edge("analyze_job", "score_job")
    graph.add_conditional_edges(
        "score_job",
        route_by_score,
        {"generate": "generate_cover", "static_cover": "static_cover", "discard": "discard_job"},
    )
    graph.add_edge("static_cover", END)
    graph.add_edge("generate_cover", "require_approval")
    graph.add_conditional_edges(
        "require_approval",
        route_by_approval,
        {"send": "send_application", "wait": END},
    )
    graph.add_edge("send_application", END)
    graph.add_edge("discard_job", END)

    if not use_checkpointing:
        return graph.compile()

    try:
        from langgraph.checkpoint.redis import RedisSaver
        from services.api.core.config import get_settings

        settings = get_settings()
        saver = RedisSaver.from_conn_string(
            settings.celery_result_backend,
            ttl={"default_ttl": 86400},  # 24 h
        )
        return graph.compile(checkpointer=saver)
    except Exception as exc:
        logger.warning("workflow_checkpointing_unavailable", error=str(exc))
        return graph.compile()
