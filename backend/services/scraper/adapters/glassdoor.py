"""Glassdoor scraper adapter — full implementation.

NOTE: Strongly recommend using a proxy for production — Glassdoor aggressively
blocks scrapers without proxies. Set PROXY_URL in .env.
"""
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import re
import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)


class GlassdoorAdapter(BaseAdapter):
    PORTAL_NAME = "glassdoor"
    REQUESTS_PER_MINUTE = 5  # conservative — Glassdoor blocks aggressively
    CONCURRENT_BROWSERS = 1

    BASE_URL = "https://www.glassdoor.co.in"

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        jobs: list[RawJob] = []
        page = 1

        title_slug = query.job_title.replace(" ", "-")
        loc_slug = (query.location or "India").replace(" ", "-")

        async with self._browser_session():
            while len(jobs) < query.max_results:
                url = (
                    f"{self.BASE_URL}/Job/jobs.htm"
                    f"?sc.keyword={quote_plus(query.job_title)}"
                    f"&locT=N&locId=0"
                    f"&jobType=all"
                    f"&fromAge=7"
                    f"&p={page}"
                )

                if not await self._can_fetch(url):
                    logger.warning("robots_blocked", url=url, portal=self.PORTAL_NAME)
                    break

                await self._rate_limit()
                logger.info("scraping_page", portal=self.PORTAL_NAME, url=url, page=page)

                try:
                    html = await self._get_page_html(url, wait_selector="li.react-job-listing")
                except Exception as exc:
                    logger.warning("page_fetch_error", url=url, error=str(exc))
                    break

                soup = BeautifulSoup(html, "lxml")
                cards = soup.select("li.react-job-listing")
                if not cards:
                    break

                for card in cards:
                    job = self._parse_job_card(card)
                    if job:
                        jobs.append(job)
                    if len(jobs) >= query.max_results:
                        break

                page += 1

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    def _parse_job_card(self, card) -> Optional[RawJob]:
        try:
            link_el = card.select_one("a.jobLink")
            if not link_el:
                link_el = card.select_one("a[data-test='job-link']")
            if not link_el:
                return None

            title_el = link_el.select_one("span") or link_el
            title = title_el.get_text(strip=True)
            href = link_el.get("href", "")
            url = href if href.startswith("http") else self.BASE_URL + href

            company_el = card.select_one("div.jobHeader a.jobEmpolyerName") or card.select_one("a.employer-name")
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = card.select_one("span.loc") or card.select_one("span[data-test='emp-location']")
            location = loc_el.get_text(strip=True) if loc_el else None

            return RawJob(
                job_title=title,
                company=company,
                location=location,
                job_url=url,
                source_portal=self.PORTAL_NAME,
                raw_data={"source": "glassdoor_card"},
            )
        except Exception as exc:
            logger.warning("card_parse_error", error=str(exc))
            return None

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

        title_el = soup.select_one("h1[data-test='job-title']") or soup.select_one("h1.title")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        company_el = soup.select_one("div.employerName") or soup.select_one("a.employer-name")
        company = company_el.get_text(strip=True) if company_el else "Unknown"

        desc_el = soup.select_one("div.jobDescriptionContent") or soup.select_one("div[class*='desc']")
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else None

        emails = extract_emails_from_text(description or "")
        hr_email = emails[0] if emails else None

        return RawJob(
            job_title=title,
            company=company,
            job_url=url,
            source_portal=self.PORTAL_NAME,
            job_description=description,
            hr_email=hr_email,
            raw_data={"source": "glassdoor_detail"},
        )
