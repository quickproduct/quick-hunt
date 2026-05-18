"""Search router — job search, scraping, and portal management."""
import asyncio
import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_get, cache_set
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import Candidate, SearchTask, User
from services.api.schemas.schemas import SearchRequest, SearchResponse, SearchTaskOut
from services.scraper.celery_app import VALID_PORTALS, celery_app

_SEARCH_TASKS_CACHE_TTL = 30  # seconds

router = APIRouter(prefix="/search", tags=["search"])
Auth = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=SearchResponse)
async def trigger_search(body: SearchRequest, _: Auth, db: AsyncSession = Depends(get_db)):
    # Validate portals
    invalid = [p for p in body.portals if p not in VALID_PORTALS]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid portals: {invalid}. Valid: {sorted(VALID_PORTALS)}",
        )

    # Verify candidate exists
    candidate = await db.get(Candidate, body.candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    search_task_id = str(uuid.uuid4())
    search_task = SearchTask(
        id=search_task_id,
        candidate_id=body.candidate_id,
        job_titles=body.job_titles,
        locations=body.locations,
        portals=body.portals,
        max_results_per_portal=body.max_results_per_portal,
        status="queued",
    )
    db.add(search_task)
    await db.flush()

    # Dispatch one Celery task per (title × location × portal) combination
    from services.scraper.tasks import scrape_portal_task

    celery_task_ids = []
    for title in body.job_titles:
        for loc in body.locations:
            for portal in body.portals:
                task = scrape_portal_task.apply_async(
                    kwargs={
                        "portal": portal,
                        "query_dict": {
                            "job_title": title,
                            "location": loc,
                            "max_results": body.max_results_per_portal,
                        },
                        "candidate_id": body.candidate_id,
                        "auto_generate_covers": body.auto_generate_covers,
                        "search_task_id": search_task_id,
                    },
                    ignore_result=True,
                )
                celery_task_ids.append(task.id)

    # Store first task ID and total count for completion tracking
    search_task.celery_task_id = celery_task_ids[0] if celery_task_ids else None
    search_task.tasks_total = len(celery_task_ids)
    search_task.status = "running"
    await db.flush()

    estimated = len(body.job_titles) * len(body.locations) * len(body.portals) * body.max_results_per_portal

    return SearchResponse(
        task_id=search_task_id,
        celery_task_ids=celery_task_ids,
        message=f"Dispatched {len(celery_task_ids)} scraping tasks across {len(body.portals)} portal(s)",
        portals=body.portals,
        estimated_jobs=estimated,
    )


@router.get("/tasks", response_model=list[SearchTaskOut])
async def list_search_tasks(
    _: Auth,
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
):
    """List recent search tasks, newest first."""
    cache_key = f"search_tasks:list:{limit}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return [SearchTaskOut(**t) for t in cached]

    result = await db.execute(
        select(SearchTask).order_by(SearchTask.created_at.desc()).limit(limit)
    )
    tasks = result.scalars().all()
    asyncio.ensure_future(
        cache_set(cache_key, [SearchTaskOut.model_validate(t).model_dump(mode="json") for t in tasks], _SEARCH_TASKS_CACHE_TTL)
    )
    return tasks


@router.get("/tasks/{task_id}", response_model=SearchTaskOut)
async def get_search_task(task_id: str, _: Auth, db: AsyncSession = Depends(get_db)):
    task = await db.get(SearchTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Search task not found")
    return task
