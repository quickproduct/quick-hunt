"""WeWorkRemotely adapter — parses the public RSS feed instead of using Playwright."""
import re
from datetime import datetime
from typing import Optional
import httpx
import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; QuickHunt/1.0)"}
_RSS_URL = "https://weworkremotely.com/categories/remote-programming-jobs.rss"


class WeWorkRemotelyAdapter(BaseAdapter):
    PORTAL_NAME = "weworkremotely"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1

    BASE_URL = "https://weworkremotely.com"

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        if not text:
            return None
        from services.scraper.date_filter import parse_relative_date
        return parse_relative_date(text)

    @staticmethod
    def _strip_html(html: str) -> str:
        return BeautifulSoup(html, "lxml").get_text(separator="\n", strip=True)

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        logger.info("scraping_page", portal=self.PORTAL_NAME, url=_RSS_URL)

        try:
            async with httpx.AsyncClient(headers=_HEADERS, follow_redirects=True, timeout=20) as client:
                resp = await client.get(_RSS_URL)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("rss_fetch_error", portal=self.PORTAL_NAME, error=str(exc))
            return []

        try:
            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")
        except Exception as exc:
            logger.warning("rss_parse_error", portal=self.PORTAL_NAME, error=str(exc))
            return []

        keywords = {w.lower() for w in query.job_title.split() if len(w) > 2}

        jobs: list[RawJob] = []
        for item in items:
            raw_title = item.find("title")
            raw_title = raw_title.get_text(strip=True) if raw_title else ""
            if not raw_title:
                continue

            # WWR title format: "Company: Job Title" — split on first colon
            if ": " in raw_title:
                company, title = raw_title.split(": ", 1)
            else:
                company, title = "Unknown", raw_title

            # Filter by query keywords
            title_lower = title.lower()
            if keywords and not any(kw in title_lower for kw in keywords):
                continue

            # Get URL from <link> — in RSS 2.0 the URL follows the <link> tag as text
            link_tag = item.find("link")
            if link_tag and link_tag.next_sibling:
                job_url = str(link_tag.next_sibling).strip()
            else:
                job_url = item.find("guid", {"isPermaLink": "true"})
                job_url = job_url.get_text(strip=True) if job_url else ""
            if not job_url.startswith("http"):
                job_url = self.BASE_URL + job_url

            raw_desc = item.find("description")
            description = self._strip_html(raw_desc.get_text() if raw_desc else "")
            emails = extract_emails_from_text(description)

            pub_date = item.find("pubDate")
            posted = self._parse_date(pub_date.get_text(strip=True) if pub_date else "")

            region_tag = item.find("region") or item.find("category")
            location = region_tag.get_text(strip=True) if region_tag else "Remote"

            jobs.append(RawJob(
                job_title=title,
                company=company.strip(),
                location=location or "Remote",
                job_url=job_url,
                source_portal=self.PORTAL_NAME,
                job_description=description or None,
                hr_email=emails[0] if emails else None,
                posted_date=posted,
            ))
            if len(jobs) >= query.max_results:
                break

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None
