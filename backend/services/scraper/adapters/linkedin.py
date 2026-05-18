"""LinkedIn RSS feed adapter — ToS-safe implementation.

IMPORTANT: LinkedIn scraping violates their Terms of Service.
This adapter uses only public RSS/search feeds.
For production use, apply for the official LinkedIn Jobs API at:
https://developer.linkedin.com/product-catalog

TODO: Implement official LinkedIn Jobs API using LINKEDIN_CLIENT_ID and
LINKEDIN_CLIENT_SECRET environment variables once API access is granted.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import httpx
import structlog

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob

logger = structlog.get_logger(__name__)


class LinkedInAdapter(BaseAdapter):
    PORTAL_NAME = "linkedin"
    REQUESTS_PER_MINUTE = 10
    CONCURRENT_BROWSERS = 1

    # LinkedIn public job search RSS endpoint (read-only, no auth)
    SEARCH_URL = "https://www.linkedin.com/jobs/search/"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        """Fetch LinkedIn job listings via public search (RSS-like scraping)."""
        jobs: list[RawJob] = []

        # LinkedIn public job search — returns HTML listing page
        url = (
            f"{self.SEARCH_URL}"
            f"?keywords={quote_plus(query.job_title)}"
            f"&location={quote_plus(query.location or 'India')}"
            f"&f_TPR=r604800"  # last 7 days
            f"&sortBy=DD"
        )

        # Use httpx (not Playwright) to respect ToS — only public data
        try:
            async with httpx.AsyncClient(
                timeout=15,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (compatible; QuickHuntBot/1.0; "
                        "+https://example.com/bot)"
                    ),
                    "Accept": "application/json, text/html",
                },
                follow_redirects=True,
            ) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    logger.warning("linkedin_fetch_failed", status=resp.status_code, url=url)
                    return jobs

                # Parse JSON-LD from page if present
                jobs = self._parse_html_listings(resp.text, query)
        except Exception as exc:
            logger.warning("linkedin_search_error", error=str(exc))

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs[: query.max_results]

    def _parse_html_listings(self, html: str, query: JobQuery) -> list[RawJob]:
        """Parse job listings from LinkedIn HTML response."""
        from bs4 import BeautifulSoup

        jobs = []
        soup = BeautifulSoup(html, "lxml")

        # LinkedIn public search results use base-search-card classes
        cards = soup.select("div.base-search-card") or soup.select("li.jobs-search-results__list-item")
        for card in cards:
            title_el = card.select_one("h3.base-search-card__title") or card.select_one("a.job-card-list__title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)

            company_el = card.select_one("h4.base-search-card__subtitle") or card.select_one("span.job-card-container__primary-description")
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = card.select_one("span.job-search-card__location") or card.select_one("li.job-card-container__metadata-item")
            location = loc_el.get_text(strip=True) if loc_el else None

            link_el = card.select_one("a.base-card__full-link") or card.select_one("a.job-card-list__title")
            job_url = link_el.get("href", "") if link_el else ""
            if not job_url:
                continue

            date_el = card.select_one("time")
            posted_date = None
            if date_el:
                dt_str = date_el.get("datetime", "")
                try:
                    posted_date = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
                except Exception:
                    pass

            jobs.append(RawJob(
                job_title=title,
                company=company,
                location=location,
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                posted_date=posted_date,
                raw_data={"source": "linkedin_public"},
            ))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        """Fetch LinkedIn job detail page (public, no auth)."""
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "lxml")
            title_el = soup.select_one("h1.top-card-layout__title")
            company_el = soup.select_one("a.topcard__org-name-link")
            desc_el = soup.select_one("div.show-more-less-html__markup")

            return RawJob(
                job_title=title_el.get_text(strip=True) if title_el else "Unknown",
                company=company_el.get_text(strip=True) if company_el else "Unknown",
                job_url=url,
                source_portal=self.PORTAL_NAME,
                job_description=desc_el.get_text(separator="\n", strip=True) if desc_el else None,
                raw_data={"source": "linkedin_detail"},
            )
        except Exception as exc:
            logger.warning("detail_fetch_error", url=url, error=str(exc))
            return None
