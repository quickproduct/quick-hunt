"""Internshala scraper adapter — popular Indian platform for jobs and internships."""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)


class InternshalaAdapter(BaseAdapter):
    PORTAL_NAME = "internshala"
    REQUESTS_PER_MINUTE = 8
    CONCURRENT_BROWSERS = 1

    BASE_URL = "https://internshala.com"

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        if not text:
            return None
        from services.scraper.date_filter import parse_relative_date
        return parse_relative_date(text)

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        jobs: list[RawJob] = []
        page = 1
        # Internshala uses slug-style search
        slug = re.sub(r"[^a-z0-9]+", "-", query.job_title.lower()).strip("-")

        async with self._browser_session():
            while len(jobs) < query.max_results:
                url = f"{self.BASE_URL}/jobs/{slug}-jobs-in-{re.sub(r'[^a-z0-9]+', '-', (query.location or 'india').lower()).strip('-')}/{page}"
                if page == 1:
                    url = f"{self.BASE_URL}/jobs/{slug}-jobs"

                if not await self._can_fetch(url):
                    break

                await self._rate_limit()
                logger.info("scraping_page", portal=self.PORTAL_NAME, url=url, page=page)

                try:
                    html = await self._get_page_html(url, wait_selector="div.individual_internship, div.job-internship-card")
                except Exception as exc:
                    logger.warning("page_fetch_error", url=url, error=str(exc))
                    break

                soup = BeautifulSoup(html, "lxml")
                cards = (
                    soup.select("div.individual_internship")
                    or soup.select("div.job-internship-card")
                    or soup.select("div[class*='internship_meta']")
                )
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
            title_el = (
                card.select_one("h3.job-internship-name a")
                or card.select_one("a.job-title-href")
                or card.select_one("h3 a")
                or card.select_one("a[href*='/jobs/detail/']")
            )
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            url = href if href.startswith("http") else self.BASE_URL + href

            company_el = (
                card.select_one("h4 a")
                or card.select_one("p.company-name")
                or card.select_one("[class*='company-name']")
            )
            company = company_el.get_text(strip=True) if company_el else "Unknown"

            loc_el = (
                card.select_one("div.location_link")
                or card.select_one("a[class*='location']")
                or card.select_one("[class*='location']")
            )
            location = loc_el.get_text(strip=True) if loc_el else None

            date_el = card.select_one("div.posted-by-container span") or card.select_one("[class*='posted']")
            posted = self._parse_date(date_el.get_text(strip=True) if date_el else "")

            return RawJob(
                job_title=title,
                company=company,
                location=location,
                job_url=url,
                source_portal=self.PORTAL_NAME,
                posted_date=posted,
            )
        except Exception as exc:
            logger.warning("card_parse_error", portal=self.PORTAL_NAME, error=str(exc))
            return None

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        if not await self._can_fetch(url):
            return None
        await self._rate_limit()
        try:
            html = await self._get_page_html(url, wait_selector="div.internship-heading-container, div[class*='jd-detail']")
        except Exception as exc:
            logger.warning("detail_fetch_error", url=url, error=str(exc))
            return None

        soup = BeautifulSoup(html, "lxml")
        title_el = soup.select_one("h1.profile") or soup.select_one("h1")
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        company_el = soup.select_one("div.company-name a") or soup.select_one("[class*='company-name']")
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        company_href = company_el.get("href", "") if company_el else ""
        company_website = company_href if company_href.startswith("http") else None

        desc_el = (
            soup.select_one("div.internship-details div.text-container")
            or soup.select_one("div[class*='about-company']")
            or soup.select_one("div.container-fluid.detail-wrapper")
        )
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else None

        emails = extract_emails_from_text(description or "")
        return RawJob(
            job_title=title,
            company=company,
            job_url=url,
            source_portal=self.PORTAL_NAME,
            job_description=description,
            hr_email=emails[0] if emails else None,
            company_website=company_website,
        )
