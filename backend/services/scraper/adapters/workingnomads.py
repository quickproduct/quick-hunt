"""WorkingNomads adapter — uses the public JSON API instead of Playwright."""
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import httpx
import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuickHunt/1.0)",
    "Accept": "application/json",
}

_API_URL = "https://www.workingnomads.com/api/exposed_jobs/"


class WorkingNomadsAdapter(BaseAdapter):
    PORTAL_NAME = "workingnomads"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        if not text:
            return None
        from services.scraper.date_filter import parse_relative_date
        return parse_relative_date(text)

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        # The free API doesn't support keyword search — fetch dev category and filter.
        url = f"{_API_URL}?category=development&region=worldwide"
        logger.info("scraping_page", portal=self.PORTAL_NAME, url=url)

        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("api_fetch_error", portal=self.PORTAL_NAME, error=str(exc))
            return []

        # Filter client-side by query keywords
        keywords = {w.lower() for w in query.job_title.split() if len(w) > 2}

        jobs: list[RawJob] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            if not title:
                continue
            title_lower = title.lower()
            if not any(kw in title_lower for kw in keywords):
                continue

            description = item.get("description", "")
            emails = extract_emails_from_text(description or "")
            job_url = item.get("url", "")

            jobs.append(RawJob(
                job_title=title,
                company=item.get("company_name", "Unknown"),
                location=item.get("location") or "Remote",
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=emails[0] if emails else None,
                company_website=item.get("company_url") or item.get("company_website") or None,
                posted_date=self._parse_date(item.get("pub_date", "")),
                raw_data={"tags": item.get("tags", []), "category": item.get("category_name", "")},
            ))
            if len(jobs) >= query.max_results:
                break

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
