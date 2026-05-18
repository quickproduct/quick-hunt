"""Wellfound (AngelList) scraper adapter — full implementation.

Good for startup and remote job listings.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)


class AngelListAdapter(BaseAdapter):
    PORTAL_NAME = "angellist"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1

    BASE_URL = "https://wellfound.com"

    # Role slug map for common titles
    _ROLE_MAP = {
        "software engineer": "software-engineer",
        "backend engineer": "backend-engineer",
        "frontend engineer": "frontend-engineer",
        "full stack engineer": "full-stack-engineer",
        "data scientist": "data-scientist",
        "product manager": "product-manager",
        "designer": "designer",
        "devops engineer": "devops-engineer",
    }

    def _title_to_slug(self, title: str) -> str:
        lower = title.lower().strip()
        return self._ROLE_MAP.get(lower, lower.replace(" ", "-"))

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        jobs: list[RawJob] = []
        page = 1
        role_slug = self._title_to_slug(query.job_title)

        async with self._browser_session():
            while len(jobs) < query.max_results:
                url = f"{self.BASE_URL}/role/{role_slug}?page={page}"
                if query.location:
                    url += f"&location={quote_plus(query.location)}"

                if not await self._can_fetch(url):
                    logger.warning("robots_blocked", url=url, portal=self.PORTAL_NAME)
                    break

                await self._rate_limit()
                logger.info("scraping_page", portal=self.PORTAL_NAME, url=url, page=page)

                try:
                    html = await self._get_page_html(url, wait_selector="div[data-test='StartupResult']")
                except Exception as exc:
                    logger.warning("page_fetch_error", url=url, error=str(exc))
                    break

                soup = BeautifulSoup(html, "lxml")
                startup_cards = soup.select("div[data-test='StartupResult']")
                if not startup_cards:
                    break

                for startup_card in startup_cards:
                    startup_jobs = self._parse_startup_card(startup_card)
                    jobs.extend(startup_jobs)
                    if len(jobs) >= query.max_results:
                        break

                page += 1

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs[: query.max_results]

    def _parse_startup_card(self, card) -> list[RawJob]:
        """Parse one startup block (may contain multiple job listings)."""
        jobs = []
        try:
            company_el = card.select_one("h2[data-test='startup-name']") or card.select_one("a.name")
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            company_link = card.select_one("a[data-test='startup-show-link']") or card.select_one("a.name")
            company_href = company_link.get("href", "") if company_link else ""
            company_website = f"{self.BASE_URL}{company_href}" if company_href.startswith("/") else company_href

            job_listings = card.select("div[data-test='job-listing']")
            for listing in job_listings:
                title_el = listing.select_one("span[data-test='title']") or listing.select_one("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)

                job_link = listing.select_one("a")
                href = job_link.get("href", "") if job_link else ""
                job_url = f"{self.BASE_URL}{href}" if href.startswith("/") else href
                if not job_url:
                    continue

                loc_el = listing.select_one("span[data-test='location']") or listing.select_one("span.location")
                location = loc_el.get_text(strip=True) if loc_el else None

                salary_el = listing.select_one("span[data-test='compensation']")
                salary_text = salary_el.get_text(strip=True) if salary_el else ""

                jobs.append(RawJob(
                    job_title=title,
                    company=company,
                    location=location,
                    job_url=job_url,
                    source_portal=self.PORTAL_NAME,
                    company_website=company_website,
                    raw_data={"salary_text": salary_text, "source": "angellist_card"},
                ))
        except Exception as exc:
            logger.warning("startup_card_parse_error", error=str(exc))
        return jobs

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        if not await self._can_fetch(url):
            return None
        await self._rate_limit()
        try:
            html = await self._get_page_html(url)
        except Exception as exc:
            logger.warning("detail_fetch_error", url=url, error=str(exc))
            return None

        soup = BeautifulSoup(html, "lxml")

        title_el = soup.select_one("h1[data-test='role-name']") or soup.select_one("h1.title")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        company_el = soup.select_one("a[data-test='company-link']") or soup.select_one("h2.company-name")
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        desc_el = soup.select_one("div[data-test='role-description']") or soup.select_one("div.description")
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else None

        company_link = soup.select_one("a[data-test='company-link']")
        company_href = company_link.get("href", "") if company_link else ""
        company_website = f"{self.BASE_URL}{company_href}" if company_href.startswith("/") else company_href

        emails = extract_emails_from_text(description or "")
        hr_email = emails[0] if emails else None

        return RawJob(
            job_title=title,
            company=company,
            job_url=url,
            source_portal=self.PORTAL_NAME,
            job_description=description,
            hr_email=hr_email,
            company_website=company_website or None,
            raw_data={"source": "angellist_detail"},
        )
