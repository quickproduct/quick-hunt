"""Tests for admin/MCP operator preview and cleanup helpers."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from services.api.models.db import Job
from services.api.routers.admin import (
    ActionRunRequest,
    _preview_cleanup,
    ignore_non_php_jobs,
)


def _job(**overrides):
    uid = uuid.uuid4().hex
    data = {
        "id": str(uuid.uuid4()),
        "job_title": "React Frontend Engineer",
        "company": f"Company {uid[:6]}",
        "location": "Remote",
        "job_description": "Build React and TypeScript interfaces.",
        "job_url": f"https://example.com/jobs/{uid}",
        "source_portal": "naukri",
        "status": "new",
        "dedupe_hash": uid,
    }
    data.update(overrides)
    return Job(**data)


@pytest.mark.asyncio
async def test_preview_non_php_jobs_does_not_mutate(db_session):
    non_php = _job()
    php = _job(
        job_title="Laravel Developer",
        job_description="Build PHP and Laravel applications.",
        dedupe_hash=uuid.uuid4().hex,
    )
    db_session.add_all([non_php, php])
    await db_session.commit()

    preview = await _preview_cleanup("non_php", db_session, limit=10)

    assert preview["would_affect_count"] == 1
    assert preview["samples"][0]["id"] == non_php.id

    refreshed = await db_session.get(Job, non_php.id)
    assert refreshed.status == "new"


@pytest.mark.asyncio
async def test_ignore_non_php_jobs_requires_confirmation(db_session):
    with pytest.raises(HTTPException) as exc:
        await ignore_non_php_jobs(object(), ActionRunRequest(confirm=False), db_session)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_ignore_non_php_jobs_marks_filtered_not_deleted(db_session):
    non_php = _job()
    db_session.add(non_php)
    await db_session.commit()

    result = await ignore_non_php_jobs(
        object(),
        ActionRunRequest(confirm=True, limit=10),
        db_session,
    )

    assert result["updated"] == 1
    rows = (await db_session.execute(select(Job).where(Job.id == non_php.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == "filtered"
