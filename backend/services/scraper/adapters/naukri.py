"""Naukri.com adapter — uses the internal v2 JSON API (no Playwright required).

Naukri's /jobapi/v2/search endpoint is the same API their website calls.
It returns structured JSON including job title, company, description, salary,
and apply URL.  Requires appid/systemid headers but no authentication.
"""
import math
from datetime import datetime
from typing import Optional

import httpx
import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_API_URL = "https://www.naukri.com/jobapi/v2/search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "appid": "109",
    "systemid": "109",
    "Accept": "application/json",
    "Referer": "https://www.naukri.com/",
}
_PER_PAGE = 20


class NaukriAdapter(BaseAdapter):
    PORTAL_NAME = "naukri"
    REQUESTS_PER_MINUTE = 20

    # ------------------------------------------------------------------ #
    # Salary parsing                                                       #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_salary(raw_min, raw_max) -> tuple[Optional[float], Optional[float], Optional[str]]:
        """Convert Naukri int salary fields (Lakhs) to absolute INR."""
        try:
            lo = float(raw_min) if raw_min else 0.0
            hi = float(raw_max) if raw_max else 0.0
        except (TypeError, ValueError):
            return None, None, None
        if lo == 0 and hi == 0:
            return None, None, None
        # Naukri stores salary in Lakhs per annum; convert to rupees
        multiplier = 100_000
        return lo * multiplier or None, hi * multiplier or None, "INR"

    # ------------------------------------------------------------------ #
    # Date parsing                                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_date(raw: str) -> Optional[datetime]:
        """Parse Naukri addDate string: '2026-04-16 22:57:36.0'."""
        if not raw:
            return None
        from services.scraper.date_filter import parse_relative_date
        return parse_relative_date(raw)

    # ------------------------------------------------------------------ #
    # Search                                                               #
    # ------------------------------------------------------------------ #
    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        location = query.location or "india"
        pages_needed = max(1, math.ceil(query.max_results / _PER_PAGE))
        jobs: list[RawJob] = []

        logger.info("scraping_page", portal=self.PORTAL_NAME,
                    url=_API_URL, keyword=query.job_title, location=location)

        async with httpx.AsyncClient(
            headers=_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            for page in range(1, pages_needed + 1):
                params = {
                    "noOfResults": _PER_PAGE,
                    "keyword": query.job_title,
                    "location": location,
                    "pageNo": page,
                }
                try:
                    resp = await client.get(_API_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                except Exception as exc:
                    logger.warning("api_fetch_error", portal=self.PORTAL_NAME,
                                   page=page, error=str(exc))
                    break

                items = data.get("list", [])
                if not items:
                    break

                for item in items:
                    job = self._parse_item(item)
                    if job:
                        jobs.append(job)
                    if len(jobs) >= query.max_results:
                        break

                if len(jobs) >= query.max_results:
                    break

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    def _parse_item(self, item: dict) -> Optional[RawJob]:
        try:
            title = item.get("post", "").strip()
            if not title:
                return None

            company = item.get("companyName", "Unknown").strip()
            city = item.get("city", "") or "India"
            job_url = item.get("urlStr", "").strip()
            description = item.get("jobDesc", "") or ""
            keywords = item.get("keywords", "") or ""

            sal_min, sal_max, sal_cur = self._parse_salary(
                item.get("minSal"), item.get("maxSal")
            )
            posted_date = self._parse_date(item.get("addDate", ""))

            emails = extract_emails_from_text(description)

            return RawJob(
                job_title=title,
                company=company,
                location=city,
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=emails[0] if emails else None,
                salary_min=sal_min,
                salary_max=sal_max,
                salary_currency=sal_cur,
                posted_date=posted_date,
                raw_data={"keywords": keywords},
            )
        except Exception as exc:
            logger.warning("item_parse_error", portal=self.PORTAL_NAME, error=str(exc))
            return None

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        # Description is already included in the API response.
        return None
