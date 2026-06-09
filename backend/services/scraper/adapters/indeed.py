"""Indeed India scraper adapter — full implementation."""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus, urlparse, parse_qs

import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob, extract_emails_from_text

logger = structlog.get_logger(__name__)


class IndeedAdapter(BaseAdapter):
    PORTAL_NAME = "indeed"
    REQUESTS_PER_MINUTE = 6
    CONCURRENT_BROWSERS = 1
    # Indeed detail pages are JS-rendered and bot-walled — plain HTTP returns
    # a challenge page, so skip straight to the browser.
    DETAIL_HTTP_FIRST = False

    BASE_URL = "https://in.indeed.com"

    @staticmethod
    def _parse_date(text: str) -> Optional[datetime]:
        """Parse Indeed relative date strings."""
        if not text:
            return None
        from services.scraper.date_filter import parse_relative_date
        parsed = parse_relative_date(text)
        if parsed:
            return parsed
        return None

    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        jobs: list[RawJob] = []
        start = 0
        per_page = 15

        async with self._browser_session():
            while len(jobs) < query.max_results:
                url = (
                    f"{self.BASE_URL}/jobs"
                    f"?q={quote_plus(query.job_title)}"
                    f"&l={quote_plus(query.location or 'India')}"
                    f"&start={start}"
                    f"&sort=date"
                )
                if not await self._can_fetch(url):
                    logger.warning("robots_blocked", url=url, portal=self.PORTAL_NAME)
                    break

                await self._rate_limit()
                logger.info("scraping_page", portal=self.PORTAL_NAME, url=url, start=start)

                try:
                    html = await self._get_page_html(url, wait_selector="div.job_seen_beacon")
                except Exception as exc:
                    logger.warning("page_fetch_error", url=url, error=str(exc))
                    break

                soup = BeautifulSoup(html, "lxml")
                cards = soup.select("div.job_seen_beacon")
                if not cards:
                    break

                for card in cards:
                    job = self._parse_job_card(card)
                    if job:
                        jobs.append(job)
                    if len(jobs) >= query.max_results:
                        break

                start += per_page

        logger.info("search_complete", portal=self.PORTAL_NAME, count=len(jobs))
        return jobs

    @staticmethod
    def _extract_company_from_url(url: str) -> Optional[str]:
        """Extract company name from Indeed URL's cmp= query parameter."""
        try:
            qs = parse_qs(urlparse(url).query)
            cmp = qs.get("cmp", [None])[0]
            if cmp:
                return cmp.replace("-", " ").replace("+", " ").strip()
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_company_from_description(description: str) -> Optional[str]:
        """Extract company name from first lines of job description."""
        if not description:
            return None
        # "About CompanyName" / "About CompanyName:" at start of a paragraph
        m = re.search(r"(?:^|\n)About\s+([A-Z][A-Za-z0-9\s&.,'-]{2,50}?)(?:\n|:|\?|$)", description)
        if m:
            return m.group(1).strip().rstrip(".,:")
        # "[CompanyName] is hiring / is looking / is a"
        m = re.search(r"^([A-Z][A-Za-z0-9\s&.'-]{2,40}?)\s+(?:is hiring|is looking|is a |are looking|are hiring)", description)
        if m:
            return m.group(1).strip()
        return None

    def _parse_job_card(self, card) -> Optional[RawJob]:
        try:
            title_el = card.select_one("h2.jobTitle a")
            if not title_el:
                return None
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            if href.startswith("/"):
                url = self.BASE_URL + href
            else:
                url = href

            # Indeed periodically renames their CSS classes; try multiple selectors
            company = None
            for sel in (
                "span.companyName",
                "[data-testid='company-name']",
                "a[data-testid='company-name']",
                "span[class*='companyName']",
                "div[class*='company'] span",
                "span[class*='company']",
            ):
                el = card.select_one(sel)
                if el:
                    text = el.get_text(strip=True)
                    if text and text.lower() != "unknown":
                        company = text
                        break

            # Fallback: extract from URL cmp= parameter
            if not company:
                company = self._extract_company_from_url(url)

            company = company or "Unknown"

            loc_el = card.select_one("div.companyLocation")
            if not loc_el:
                loc_el = card.select_one("[data-testid='text-location']")
            location = loc_el.get_text(strip=True) if loc_el else None

            salary_el = card.select_one("div.metadata.salary-snippet-container")
            salary_text = salary_el.get_text(strip=True) if salary_el else ""

            date_el = card.select_one("span.date")
            if not date_el:
                date_el = card.select_one("[data-testid='myJobsStateDate']")
            posted = self._parse_date(date_el.get_text(strip=True) if date_el else "")

            return RawJob(
                job_title=title,
                company=company,
                location=location,
                job_url=url,
                source_portal=self.PORTAL_NAME,
                posted_date=posted,
                raw_data={"salary_text": salary_text, "source": "indeed_card"},
            )
        except Exception as exc:
            logger.warning("card_parse_error", error=str(exc))
            return None

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        if not await self._can_fetch(url):
            return None
        await self._rate_limit()
        try:
            html = await self._get_page_html(url, wait_selector="div#jobDescriptionText")
        except Exception as exc:
            logger.warning("detail_fetch_error", url=url, error=str(exc))
            return None

        soup = BeautifulSoup(html, "lxml")

        title_el = (
            soup.select_one("h1.jobsearch-JobInfoHeader-title")
            or soup.select_one("h1[data-testid='jobsearch-JobInfoHeader-title']")
            or soup.select_one("h1")
        )
        title = title_el.get_text(strip=True) if title_el else "Unknown"

        company_el = (
            soup.select_one("div.jobsearch-CompanyInfoContainer a")
            or soup.select_one("[data-testid='inlineHeader-companyName'] a")
            or soup.select_one("[data-testid='inlineHeader-companyName']")
            or soup.select_one("div[data-company-name='true']")
        )
        company = company_el.get_text(strip=True) if company_el else "Unknown"
        company_href = company_el.get("href", "") if company_el else ""
        company_website = company_href if company_href.startswith("http") else None

        desc_el = (
            soup.select_one("div#jobDescriptionText")
            or soup.select_one("[data-testid='jobDescriptionText']")
        )
        description = desc_el.get_text(separator="\n", strip=True) if desc_el else None

        # If company still unknown, try extracting from description
        if company == "Unknown" and description:
            extracted = self._extract_company_from_description(description)
            if extracted:
                company = extracted

        loc_el = (
            soup.select_one("div.jobsearch-JobInfoHeader-subtitle div.jobsearch-JobInfoHeader-locationWrapper")
            or soup.select_one("[data-testid='job-location']")
        )
        location = loc_el.get_text(strip=True) if loc_el else None

        emails = extract_emails_from_text(description or "")
        hr_email = emails[0] if emails else None

        return RawJob(
            job_title=title,
            company=company,
            location=location,
            job_url=url,
            source_portal=self.PORTAL_NAME,
            job_description=description,
            hr_email=hr_email,
            company_website=company_website,
            raw_data={"source": "indeed_detail"},
        )
