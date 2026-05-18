"""Shine.com adapter — extracts job listings from server-side rendered __NEXT_DATA__.

Shine uses Next.js and server-renders the first page of results into
__NEXT_DATA__ JSON.  This gives us 20 jobs per request without Playwright.
The data is at: props.pageProps.initialState.jsrp.searchresult.data.results
"""
import json
import re
from datetime import datetime
from typing import Optional

import httpx
import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_BASE_URL = "https://www.shine.com/job-search"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.shine.com/",
}


def _build_slug(query: JobQuery) -> str:
    """Build Shine search URL slug: 'PHP Developer' + 'Mumbai' → 'php-developer-jobs-in-mumbai'."""
    title = re.sub(r"[^a-z0-9]+", "-", query.job_title.lower()).strip("-")
    loc = query.location or ""
    if loc and loc.lower() not in ("remote", "any", "all", ""):
        loc_slug = re.sub(r"[^a-z0-9]+", "-", loc.lower()).strip("-")
        return f"{title}-jobs-in-{loc_slug}"
    return f"{title}-jobs-in-india"


def _parse_date(raw: str) -> Optional[datetime]:
    """Parse ISO-ish date from Shine: '2026-02-27T05:35:12'."""
    if not raw:
        return None
    from services.scraper.date_filter import parse_relative_date
    return parse_relative_date(raw)


def _extract_results(html: str) -> list[dict]:
    """Pull job results from the __NEXT_DATA__ script tag."""
    soup = BeautifulSoup(html, "html.parser")
    nd = soup.find("script", id="__NEXT_DATA__")
    if not nd:
        return []
    try:
        data = json.loads(nd.get_text())
        return (
            data.get("props", {})
                .get("pageProps", {})
                .get("initialState", {})
                .get("jsrp", {})
                .get("searchresult", {})
                .get("data", {})
                .get("results", [])
        )
    except Exception:
        return []


class ShineAdapter(BaseAdapter):
    PORTAL_NAME = "shine"
    REQUESTS_PER_MINUTE = 20

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        slug = _build_slug(query)
        url = f"{_BASE_URL}/{slug}/"
        logger.info("scraping_page", portal=self.PORTAL_NAME, url=url)

        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, timeout=25, follow_redirects=True, verify=False
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("fetch_error", portal=self.PORTAL_NAME, url=url, error=str(exc))
            return []

        results = _extract_results(resp.text)
        if not results:
            logger.warning("no_results_in_next_data", portal=self.PORTAL_NAME, url=url)
            return []

        jobs: list[RawJob] = []
        for item in results:
            if len(jobs) >= query.max_results:
                break
            job = self._parse_item(item)
            if job:
                jobs.append(job)

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    def _parse_item(self, item: dict) -> Optional[RawJob]:
        try:
            title = (item.get("jJT") or "").strip()
            if not title:
                return None

            company = (item.get("jCName") or "Unknown").strip()

            loc = item.get("jLoc")
            if isinstance(loc, list):
                location = ", ".join(loc[:3])
            else:
                location = (loc or "India")

            slug = item.get("jSlug", "")
            job_url = f"https://www.shine.com/jobs/{slug}" if slug else ""

            description = item.get("jJD", "") or ""
            email = item.get("jRE", "") or ""
            from services.common.placeholder_emails import PLACEHOLDER_EMAILS
            if email and "@" in email and email.lower() not in PLACEHOLDER_EMAILS:
                hr_email = email
            else:
                emails = extract_emails_from_text(description)
                hr_email = emails[0] if emails else None

            posted_date = _parse_date(item.get("jPDate", ""))

            return RawJob(
                job_title=title,
                company=company,
                location=location,
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=hr_email,
                posted_date=posted_date,
                raw_data={
                    "salary": item.get("jSal"),
                    "keywords": item.get("jKwd"),
                    "experience": item.get("jExp"),
                },
            )
        except Exception as exc:
            logger.warning("item_parse_error", portal=self.PORTAL_NAME, error=str(exc))
            return None

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        # Description is already included in __NEXT_DATA__.
        return None
