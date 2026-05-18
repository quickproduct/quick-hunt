"""Pytest fixtures — async SQLite in-memory engine, sample data, async HTTP client."""
import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# Force test settings before any imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("ADMIN_API_KEY", "test-api-key")
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("VECTOR_DB_PROVIDER", "local")
os.environ.setdefault("EMAIL_PROVIDER", "smtp")
os.environ.setdefault("CELERY_BROKER_URL", "memory://")
os.environ.setdefault("CELERY_RESULT_BACKEND", "cache+memory://")

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from services.api.core.database import Base
from services.api.models.db import Candidate, Job


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    """Create a session-scoped event loop."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_candidate_data():
    return {
        "name": "Jane Smith",
        "email": f"jane_{uuid.uuid4().hex[:8]}@example.com",
        "skills": ["Python", "FastAPI", "PostgreSQL", "Redis"],
        "years_experience": 4,
        "target_roles": ["Backend Engineer", "Senior Python Developer"],
        "target_locations": ["Bangalore", "Remote"],
        "bio": "Experienced backend engineer with 4 years in Python.",
    }


@pytest.fixture
def sample_job_data():
    uid = uuid.uuid4().hex[:8]
    return {
        "job_title": "Senior Python Engineer",
        "company": "TechCorp Solutions",
        "location": "Bangalore, Karnataka",
        "job_description": "We are looking for a senior Python engineer with experience in FastAPI, PostgreSQL, and microservices. Contact hr@techcorp.com for details.",
        "job_url": f"https://www.naukri.com/job-listings-senior-python-engineer-{uid}",
        "source_portal": "naukri",
        "status": "new",
        "dedupe_hash": uid,
        "hr_email": "hr@techcorp.com",
        "company_website": "https://techcorp.com",
        "salary_min": 1200000.0,
        "salary_max": 1800000.0,
        "salary_currency": "INR",
        "experience_required": "3-6 years",
    }


@pytest_asyncio.fixture
async def saved_candidate(db_session, sample_candidate_data):
    candidate = Candidate(id=str(uuid.uuid4()), **sample_candidate_data)
    db_session.add(candidate)
    await db_session.commit()
    return candidate


@pytest_asyncio.fixture
async def saved_job(db_session, sample_job_data, saved_candidate):
    job = Job(id=str(uuid.uuid4()), candidate_id=saved_candidate.id, **sample_job_data)
    db_session.add(job)
    await db_session.commit()
    return job


@pytest_asyncio.fixture
async def async_client():
    """httpx AsyncClient pointed at the FastAPI test app."""
    from httpx import AsyncClient, ASGITransport
    from services.api.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": "test-api-key"},
    ) as client:
        yield client
