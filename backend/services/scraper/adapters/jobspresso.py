"""Jobspresso adapter — uses the WordPress REST API instead of Playwright."""
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import httpx
import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; QuickHunt/1.0)",
    "Accept": "application/json",
}
_API_BASE = "https://jobspresso.co/wp-json/wp/v2/job-listings"


class JobspressoAdapter(BaseAdapter):
    PORTAL_NAME = "jobspresso"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1

    BASE_URL = "https://jobspresso.co"

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        if not text:
            return None
        from services.scraper.date_filter import parse_relative_date
        return parse_relative_date(text)

    @staticmethod
    def _strip_html(html: str) -> str:
        return BeautifulSoup(html or "", "lxml").get_text(separator="\n", strip=True)

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        page, per_page = 1, 100
        url = f"{_API_BASE}?per_page={per_page}&search={quote_plus(query.job_title)}&page={page}"
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
            title = item.get("title", {}).get("rendered", "")
            if not title:
                continue
            title = BeautifulSoup(title, "lxml").get_text(strip=True)

            job_url = item.get("link", "")
            description = self._strip_html(item.get("content", {}).get("rendered", ""))
            emails = extract_emails_from_text(description)

            # Meta fields from WP job-manager
            meta = item.get("meta", {})
            company = meta.get("_company_name", [""])[0] if isinstance(meta.get("_company_name"), list) else meta.get("_company_name", "Unknown")
            location = meta.get("_job_location", ["Remote"])[0] if isinstance(meta.get("_job_location"), list) else meta.get("_job_location", "Remote")
            _cw = meta.get("_company_website")
            company_website = (_cw[0] if _cw else None) if isinstance(_cw, list) else (_cw or None)

            jobs.append(RawJob(
                job_title=title,
                company=company or "Unknown",
                location=location or "Remote",
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=emails[0] if emails else None,
                company_website=company_website,
                posted_date=self._parse_date(item.get("date", "")),
            ))
            if len(jobs) >= query.max_results:
                break

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
