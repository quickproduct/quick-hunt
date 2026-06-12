"""Candidate CRUD router."""
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.core.cache import cache_delete, cache_get, cache_set
from services.api.core.database import get_db
from services.api.core.dependencies import get_current_user
from services.api.models.db import Candidate, User
from services.api.schemas.schemas import CandidateCreate, CandidateOut, CandidateUpdate

_CANDIDATES_CACHE_KEY = "candidates:active"
_CANDIDATES_TTL = 300  # 5 minutes — candidates rarely change

router = APIRouter(prefix="/candidates", tags=["candidates"])
Auth = Annotated[User, Depends(get_current_user)]


@router.post("", response_model=CandidateOut, status_code=status.HTTP_201_CREATED)
async def create_candidate(body: CandidateCreate, _: Auth, db: AsyncSession = Depends(get_db)):
    # Check duplicate email
    existing = await db.execute(select(Candidate).where(Candidate.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Candidate with this email already exists")

    candidate = Candidate(id=str(uuid.uuid4()), **body.model_dump())
    db.add(candidate)
    await db.flush()
    await db.refresh(candidate)
    await cache_delete(_CANDIDATES_CACHE_KEY)
    return candidate


@router.get("", response_model=list[CandidateOut])
async def list_candidates(_: Auth, db: AsyncSession = Depends(get_db)):
    # Serve from cache — candidates rarely change, called on every page load
    cached = await cache_get(_CANDIDATES_CACHE_KEY)
    if cached is not None:
        return [CandidateOut(**c) for c in cached]

    result = await db.execute(
        select(Candidate).where(Candidate.is_active == True).order_by(Candidate.created_at.desc())  # noqa
    )
    candidates = result.scalars().all()

    import asyncio
    asyncio.ensure_future(
        cache_set(
            _CANDIDATES_CACHE_KEY,
            [CandidateOut.model_validate(c).model_dump() for c in candidates],
            _CANDIDATES_TTL,
        )
    )
    return candidates


@router.get("/{candidate_id}", response_model=CandidateOut)
async def get_candidate(candidate_id: str, _: Auth, db: AsyncSession = Depends(get_db)):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


@router.put("/{candidate_id}", response_model=CandidateOut)
async def update_candidate(
    candidate_id: str, body: CandidateUpdate, _: Auth, db: AsyncSession = Depends(get_db)
):
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(candidate, field, value)
    await db.flush()
    await db.refresh(candidate)
    await cache_delete(_CANDIDATES_CACHE_KEY)
    return candidate


_RESUMES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "resumes"
_MAX_RESUME_BYTES = 5 * 1024 * 1024


@router.post("/{candidate_id}/resume", response_model=CandidateOut)
async def upload_resume(
    candidate_id: str,
    _: Auth,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload a PDF resume for a candidate. Saves to backend/resumes/ and updates resume_url."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=422, detail="Only PDF files are accepted")

    content = await file.read(_MAX_RESUME_BYTES + 1)
    if len(content) > _MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume must be 5MB or smaller")
    if not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=422, detail="File is not a valid PDF")

    # Derive a clean filename from the candidate name
    safe_name = candidate.name.lower().replace(" ", "-")
    filename = f"{safe_name}-resume.pdf"

    _RESUMES_DIR.mkdir(parents=True, exist_ok=True)
    dest = _RESUMES_DIR / filename
    dest.write_bytes(content)

    candidate.resume_url = f"resumes/{filename}"
    await db.flush()
    await db.refresh(candidate)
    await cache_delete(_CANDIDATES_CACHE_KEY)
    return candidate


@router.get("/{candidate_id}/resume")
async def download_resume(
    candidate_id: str,
    _: Auth,
    db: AsyncSession = Depends(get_db),
):
    """Download the resume PDF for a candidate."""
    candidate = await db.get(Candidate, candidate_id)
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if not candidate.resume_url:
        raise HTTPException(status_code=404, detail="No resume uploaded for this candidate")

    # Strip leading "resumes/" prefix if present
    filename = candidate.resume_url.replace("resumes/", "", 1).lstrip("/")
    path = _RESUMES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Resume file not found on disk: {filename}")

    download_name = f"{candidate.name.replace(' ', '_')}_resume.pdf"
    return FileResponse(path, media_type="application/pdf", filename=download_name)
