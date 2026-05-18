"""RemoteOK adapter — uses the public JSON API instead of Playwright."""
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus

import httpx
import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuickHunt/1.0; +https://github.com/jobhunter)",
    "Accept": "application/json",
}


class RemoteOKAdapter(BaseAdapter):
    PORTAL_NAME = "remoteok"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1

    API_URL = "https://remoteok.com/api"

    @staticmethod
    def _epoch_to_dt(epoch) -> Optional[datetime]:
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except Exception:
            return None

    # Priority-ordered tech keywords to use as RemoteOK tags.
    _TAG_KEYWORDS = [
        "php", "laravel", "symfony", "wordpress", "codeigniter",
        "python", "django", "flask", "fastapi",
        "javascript", "typescript", "nodejs", "node", "react", "vue", "angular",
        "java", "kotlin", "spring",
        "ruby", "rails",
        "go", "golang",
        "rust", "scala",
        "backend", "frontend", "fullstack", "devops", "mobile",
    ]

    @classmethod
    def _build_tags(cls, query: JobQuery) -> str:
        """Extract the best RemoteOK tag from the job title.

        RemoteOK's tag search only works with single-word technology slugs
        (e.g. 'php', 'laravel') — multi-word slugs like 'php-developer' return 0.
        """
        title_lower = query.job_title.lower()
        for kw in cls._TAG_KEYWORDS:
            if kw in title_lower:
                return kw
        # Fallback: use the first word of the title
        return re.sub(r"[^a-z0-9]", "", title_lower.split()[0])

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        tags = self._build_tags(query)
        url = f"{self.API_URL}?tags={quote_plus(tags)}"
        logger.info("scraping_page", portal=self.PORTAL_NAME, url=url)

        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("api_fetch_error", portal=self.PORTAL_NAME, error=str(exc))
            return []

        jobs: list[RawJob] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            position = item.get("position", "")
            company = item.get("company", "Unknown")
            if not position:
                continue

            apply_url = item.get("apply_url") or item.get("url") or ""
            if not apply_url:
                slug = item.get("slug", "")
                apply_url = f"https://remoteok.com/remote-jobs/{slug}" if slug else ""

            description = item.get("description", "")
            emails = extract_emails_from_text(description or "")

            jobs.append(RawJob(
                job_title=position,
                company=company,
                location=item.get("location") or "Remote",
                job_url=apply_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=emails[0] if emails else None,
                company_website=item.get("company_url") or None,
                salary_min=float(item["salary_min"]) if item.get("salary_min") else None,
                salary_max=float(item["salary_max"]) if item.get("salary_max") else None,
                posted_date=self._epoch_to_dt(item.get("epoch")),
                raw_data={"tags": item.get("tags", [])},
            ))
            if len(jobs) >= query.max_results:
                break

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        # Description already included in API response — nothing extra to fetch.
        return None
