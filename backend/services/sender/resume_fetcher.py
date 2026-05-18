"""Local filesystem resume loader.

Resumes are stored in backend/resumes/ and referenced by filename.
Supported resume_url formats (stored in candidates.resume_url):
  - "resumes/suraj-shetty-software-engineer.pdf"   ← preferred (relative to backend/)
  - "suraj-shetty-software-engineer.pdf"            ← bare filename, auto-resolved
  - "http://..." / "https://..."                    ← HTTP fallback (not used in prod)
"""
import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# Absolute path to backend/resumes/ — works both on host and inside Docker container
# (docker-compose mounts ../backend → /app/backend, so this resolves correctly)
_RESUMES_DIR = Path(__file__).resolve().parent.parent.parent / "resumes"


def _resolve_local_path(resume_url: str) -> Path:
    """Return the absolute Path for a resume_url value."""
    # Strip leading slash or "resumes/" prefix to get bare filename
    name = resume_url.lstrip("/")
    if name.startswith("resumes/"):
        name = name[len("resumes/"):]
    return _RESUMES_DIR / name


def download_resume(resume_url: str) -> bytes:
    """Return PDF bytes for a candidate resume.

    Tries local disk first (preferred), falls back to HTTP for legacy URLs.
    Raises FileNotFoundError if local file is missing; raises RuntimeError for
    HTTP errors so the caller can log and continue without the attachment.
    """
    if not resume_url:
        raise ValueError("resume_url is empty")

    # HTTP/HTTPS — legacy support only (R2 URLs, external links)
    if resume_url.startswith("http://") or resume_url.startswith("https://"):
        # Attempt to resolve to a local file first by matching the filename
        filename = resume_url.rstrip("/").split("/")[-1]
        local_path = _RESUMES_DIR / filename
        if local_path.exists():
            data = local_path.read_bytes()
            logger.info("resume_loaded_local_from_url", path=str(local_path), size=len(data))
            return data

        # Genuinely remote URL — download it
        import httpx
        resp = httpx.get(resume_url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        logger.info("resume_downloaded_http", url=resume_url, size=len(resp.content))
        return resp.content

    # Local path (preferred format)
    local_path = _resolve_local_path(resume_url)
    if not local_path.exists():
        raise FileNotFoundError(
            f"Resume not found at {local_path}. "
            f"Place the PDF in backend/resumes/ and set resume_url='resumes/{local_path.name}'"
        )
    data = local_path.read_bytes()
    logger.info("resume_loaded_local", path=str(local_path), size=len(data))
    return data


def list_resumes() -> list[str]:
    """Return filenames of all PDFs in backend/resumes/."""
    if not _RESUMES_DIR.exists():
        return []
    return sorted(p.name for p in _RESUMES_DIR.iterdir() if p.suffix.lower() == ".pdf")
