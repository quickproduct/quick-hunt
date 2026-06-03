"""MNC direct career-page scraper — 8-tier strategy.

Tier  ATS              Method
────  ───              ──────
  1   greenhouse       httpx  → boards-api.greenhouse.io public JSON API
  2   lever            httpx  → api.lever.co public JSON API
  3   smartrecruiters  httpx  → api.smartrecruiters.com public JSON API
  4   workday          Playwright + BS4 (React-rendered Workday pages)
  5   icims            Playwright + BS4 (iCIMS job search pages)
  6   taleo            httpx  + BS4 (classic Taleo HTML tables)
  7   bamboohr         Playwright + BS4 (BambooHR React pages)
  8   custom           Playwright + BS4 enhanced (search-box detection,
                       multi-pattern card extraction, pagination)

All results carry source_portal='mnc_direct' and company_website=career_url.
Sending always uses candidate.static_cover_letter (enforced in sender/tasks.py).
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog
from bs4 import BeautifulSoup

from services.scraper.base_adapter import BaseAdapter, JobQuery, RawJob
from services.scraper.mnc_companies import MNC_COMPANIES, MNCCompany

logger = structlog.get_logger(__name__)

PORTAL_NAME = "mnc_direct"

_SE_KEYWORDS = re.compile(
    r"\b(software\s+engineer|software\s+developer|backend\s+engineer|"
    r"fullstack\s+engineer|full.stack\s+engineer|full.stack\s+developer|"
    r"backend\s+developer|php\s+developer|python\s+developer|web\s+developer|"
    r"sde[- ]*[12ii]?|software\s+development\s+engineer|sr\.?\s+engineer|"
    r"senior\s+engineer|staff\s+engineer|principal\s+engineer)\b",
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s{2,}")

# BeautifulSoup CSS patterns for generic career pages (most-specific first)
_GENERIC_CARD_PATTERNS = [
    "[class*='job-card'] a[href]",
    "[class*='JobCard'] a[href]",
    "[class*='job-listing'] a[href]",
    "[class*='JobListing'] a[href]",
    "[class*='job-result'] a[href]",
    "[class*='JobResult'] a[href]",
    "[class*='position-'] a[href]",
    "[class*='vacancy'] a[href]",
    "h2 a[href*='job']",
    "h3 a[href*='job']",
    "article a[href*='job']",
    "li a[href*='/careers/']",
    "li a[href*='/jobs/']",
]

# Playwright selectors to find a search box on a career page
_SEARCH_BOX_SELECTORS = [
    "input[placeholder*='search' i]",
    "input[placeholder*='job title' i]",
    "input[placeholder*='keyword' i]",
    "input[name*='search' i]",
    "input[name='q']",
    "input[type='search']",
    "input[aria-label*='search' i]",
    "input[id*='search' i]",
    "input[id*='keyword' i]",
    "#search-keyword",
    "#keyword",
    "#q",
]

# Playwright selectors for "Next page" buttons
_NEXT_PAGE_SELECTORS = [
    "a[aria-label*='Next' i]",
    "button[aria-label*='Next' i]",
    "a[title*='Next' i]",
    "a.next",
    "button.next",
    "li.next a",
    "[class*='pagination'] a:last-child",
    "[class*='Pagination'] button:last-child",
    "button[data-uxi-element-id='next']",
]


def _is_se_role(title: str) -> bool:
    return bool(_SE_KEYWORDS.search(title))


def _strip_html(html: str) -> str:
    text = _HTML_TAG_RE.sub(" ", html or "")
    return _WHITESPACE_RE.sub(" ", text).strip()


def _parse_iso(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _resolve_url(href: str, career_url: str) -> Optional[str]:
    """Turn a relative href into an absolute URL using career_url as base."""
    if not href:
        return None
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        parsed = urlparse(career_url)
        return f"{parsed.scheme}:{href}"
    if href.startswith("/"):
        parsed = urlparse(career_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    return None


def _extract_jobs_from_soup_links(
    links,  # list of BS4 Tag
    company_name: str,
    career_url: str,
    ats_meta: str = "custom",
) -> list[RawJob]:
    """Convert BS4 <a> tags to RawJob list, deduplicating by URL."""
    results: list[RawJob] = []
    seen: set[str] = set()
    for el in links:
        title = el.get_text(strip=True)
        href = _resolve_url(el.get("href", ""), career_url)
        if not title or not href or href in seen:
            continue
        seen.add(href)
        results.append(RawJob(
            job_title=title,
            company=company_name,
            job_url=href,
            source_portal=PORTAL_NAME,
            company_website=career_url,
            raw_data={"ats": ats_meta},
        ))
    return results


# ── Adapter ───────────────────────────────────────────────────────────────────

class MNCCareerAdapter(BaseAdapter):
    """Scrapes software-engineer roles from top MNC career pages."""

    PORTAL_NAME = PORTAL_NAME
    REQUESTS_PER_MINUTE = 15
    CONCURRENT_BROWSERS = 2

    # ── Public interface ───────────────────────────────────────────────────

    async def search_jobs(
        self,
        query: JobQuery,
        companies: list[dict] | None = None,
    ) -> list[RawJob]:
        # `companies` is the new DB-sourced roster from
        # `services.scraper.mnc_company_loader.load_active_mnc_companies`.
        # Falls back to the hardcoded module list only when callers don't
        # supply one (e.g. ad-hoc scripts, tests).
        if companies is None:
            companies = MNC_COMPANIES
        if query.max_results and query.max_results < len(companies):
            companies = companies[: query.max_results]
        results: list[RawJob] = []

        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            for company in companies:
                try:
                    jobs = await asyncio.wait_for(
                        self._scrape_company(client, company),
                        timeout=180,
                    )
                    results.extend(jobs)
                    logger.info("mnc_company_done", company=company["name"], found=len(jobs))
                except asyncio.TimeoutError:
                    logger.warning("mnc_company_timeout", company=company["name"], timeout_s=180)
                except Exception as exc:
                    logger.warning("mnc_company_error", company=company["name"], error=str(exc))

        return results

    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        return None

    # ── Routing ────────────────────────────────────────────────────────────

    async def _scrape_company(self, client: httpx.AsyncClient, company: MNCCompany) -> list[RawJob]:
        ats        = company.get("ats", "custom")
        career_url = company["career_url"]
        name       = company["name"]
        slug       = company.get("ats_slug", "")

        if ats == "greenhouse"      and slug: return await self._scrape_greenhouse(client, slug, name, career_url)
        if ats == "lever"           and slug: return await self._scrape_lever(client, slug, name, career_url)
        if ats == "smartrecruiters" and slug: return await self._scrape_smartrecruiters(client, slug, name, career_url)
        if ats == "workday":                  return await self._scrape_workday(name, career_url)
        if ats == "icims":                    return await self._scrape_icims(name, career_url)
        if ats == "taleo":                    return await self._scrape_taleo(client, name, career_url)
        if ats == "bamboohr":                 return await self._scrape_bamboohr(name, career_url)
        return await self._scrape_playwright_enhanced(name, career_url)

    # ── Tier 1: Greenhouse public JSON API ────────────────────────────────

    async def _scrape_greenhouse(
        self, client: httpx.AsyncClient, slug: str, company_name: str, career_url: str
    ) -> list[RawJob]:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        await self._rate_limit()
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("greenhouse_api_error", slug=slug, error=str(exc))
            return []

        results: list[RawJob] = []
        for item in resp.json().get("jobs", []):
            title = item.get("title", "")
            if not _is_se_role(title):
                continue
            job_url     = item.get("absolute_url", "") or career_url
            description = _strip_html(item.get("content", ""))
            loc_list    = item.get("offices") or item.get("location") or {}
            location    = _extract_location(loc_list)
            posted_date = _parse_iso(item.get("updated_at", ""))
            results.append(RawJob(
                job_title=title, company=company_name, job_url=job_url,
                source_portal=PORTAL_NAME, location=location,
                job_description=description, posted_date=posted_date,
                company_website=career_url,
                raw_data={"ats": "greenhouse", "gh_id": item.get("id")},
            ))
        return results

    # ── Tier 2: Lever public JSON API ─────────────────────────────────────

    async def _scrape_lever(
        self, client: httpx.AsyncClient, slug: str, company_name: str, career_url: str
    ) -> list[RawJob]:
        url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
        await self._rate_limit()
        try:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("lever_api_error", slug=slug, error=str(exc))
            return []

        items = resp.json() if isinstance(resp.json(), list) else []
        results: list[RawJob] = []
        for item in items:
            title = item.get("text", "")
            if not _is_se_role(title):
                continue
            job_url     = item.get("hostedUrl") or item.get("applyUrl") or career_url
            description = _lever_description(item)
            location    = item.get("categories", {}).get("location", "") or None
            created_at  = item.get("createdAt", 0)
            posted_date = datetime.fromtimestamp(created_at / 1000, tz=timezone.utc) if created_at else None
            results.append(RawJob(
                job_title=title, company=company_name, job_url=job_url,
                source_portal=PORTAL_NAME, location=location,
                job_description=description, posted_date=posted_date,
                company_website=career_url,
                raw_data={"ats": "lever", "lever_id": item.get("id")},
            ))
        return results

    # ── Tier 3: SmartRecruiters public JSON API ───────────────────────────

    async def _scrape_smartrecruiters(
        self, client: httpx.AsyncClient, slug: str, company_name: str, career_url: str
    ) -> list[RawJob]:
        url = (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?limit=100&q=software+engineer"
        )
        await self._rate_limit()
        try:
            resp = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
            })
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("smartrecruiters_api_error", slug=slug, error=str(exc))
            return []

        results: list[RawJob] = []
        for item in resp.json().get("content", []):
            title = item.get("name", "")
            if not _is_se_role(title):
                continue
            ref      = item.get("ref", "")
            job_url  = f"https://jobs.smartrecruiters.com/{slug}/{ref.rsplit('/', 1)[-1]}" if ref else career_url
            location = (item.get("location") or {}).get("city") or None
            results.append(RawJob(
                job_title=title, company=company_name, job_url=job_url,
                source_portal=PORTAL_NAME, location=location,
                company_website=career_url,
                raw_data={"ats": "smartrecruiters", "sr_id": item.get("id")},
            ))
        return results

    # ── Tier 4: Workday — Playwright + BS4 ───────────────────────────────

    async def _scrape_workday(self, company_name: str, career_url: str) -> list[RawJob]:
        search_url = career_url if "q=" in career_url else (
            career_url + ("&" if "?" in career_url else "?") + "q=software+engineer"
        )
        try:
            async with self._browser_session() as ctx:
                page = await ctx.new_page()
                page.set_default_timeout(15_000)
                await self._rate_limit()
                await page.goto(search_url, wait_until="domcontentloaded", timeout=25_000)
                await page.wait_for_timeout(3500)  # React hydration delay

                results: list[RawJob] = []
                for _ in range(5):  # up to 5 pages
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    # Workday uses data-automation-id attributes for stable selection
                    cards = (
                        soup.select("li[data-automation-id='jobItem']")
                        or soup.select("section[data-automation-id='jobResults'] li")
                        or soup.select("ul[role='list'] li")
                    )
                    for card in cards:
                        a = (
                            card.select_one("a[data-automation-id='jobTitle']")
                            or card.select_one("a[class*='css-'][href]")
                            or card.select_one("a[href]")
                        )
                        if not a:
                            continue
                        title = a.get_text(strip=True)
                        if not _is_se_role(title):
                            continue
                        href = _resolve_url(a.get("href", ""), search_url)
                        if not href:
                            continue
                        results.append(RawJob(
                            job_title=title, company=company_name, job_url=href,
                            source_portal=PORTAL_NAME, company_website=career_url,
                            raw_data={"ats": "workday"},
                        ))

                    # Workday "Next" button
                    next_btn = await page.query_selector(
                        "button[data-uxi-element-id='next'], "
                        "button[aria-label*='next' i], "
                        "nav a[aria-label*='next' i]"
                    )
                    if not next_btn:
                        break
                    try:
                        await next_btn.click()
                        await page.wait_for_timeout(2500)
                    except Exception:
                        break

                await page.close()
                return results
        except Exception as exc:
            logger.warning("workday_scrape_error", company=company_name, error=str(exc))
            return []

    # ── Tier 5: iCIMS — Playwright + BS4 ─────────────────────────────────

    async def _scrape_icims(self, company_name: str, career_url: str) -> list[RawJob]:
        sep = "&" if "?" in career_url else "?"
        search_url = career_url + sep + "keyword=Software+Engineer&searchCategory="
        try:
            async with self._browser_session() as ctx:
                page = await ctx.new_page()
                page.set_default_timeout(15_000)
                await self._rate_limit()
                await page.goto(search_url, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(2000)

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                links = (
                    soup.select("td.iCIMS_JobsTableJobText a[href]")
                    or soup.select("a.iCIMS_Anchor[href*='/jobs/']")
                    or soup.select("a[href*='/jobs/'][class*='iCIMS']")
                    or soup.select("div.iCIMS_Padder a[href*='/jobs/']")
                )
                results = _extract_jobs_from_soup_links(links, company_name, career_url, "icims")

                await page.close()
                return [r for r in results if _is_se_role(r.job_title)]
        except Exception as exc:
            logger.warning("icims_scrape_error", company=company_name, error=str(exc))
            return []

    # ── Tier 6: Taleo — httpx + BS4 ──────────────────────────────────────

    async def _scrape_taleo(
        self, client: httpx.AsyncClient, company_name: str, career_url: str
    ) -> list[RawJob]:
        sep = "&" if "?" in career_url else "?"
        search_url = career_url + sep + "appliedFilter.keyword=Software+Engineer"
        await self._rate_limit()
        try:
            resp = await client.get(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml",
            })
            resp.raise_for_status()
        except Exception as exc:
            logger.debug("taleo_fetch_error", company=company_name, error=str(exc))
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        results: list[RawJob] = []
        rows = (
            soup.select("tr.requisitionListInterface")
            or soup.select("table.listContainer tr")
        )
        for row in rows:
            a = (
                row.select_one("a.requisitionListInterface[href]")
                or row.select_one("a[href*='careersection']")
                or row.select_one("td:first-child a[href]")
            )
            if not a:
                continue
            title = a.get_text(strip=True)
            if not _is_se_role(title):
                continue
            href = _resolve_url(a.get("href", ""), career_url)
            if not href:
                continue
            results.append(RawJob(
                job_title=title, company=company_name, job_url=href,
                source_portal=PORTAL_NAME, company_website=career_url,
                raw_data={"ats": "taleo"},
            ))
        return results

    # ── Tier 7: BambooHR — Playwright + BS4 ──────────────────────────────

    async def _scrape_bamboohr(self, company_name: str, career_url: str) -> list[RawJob]:
        try:
            async with self._browser_session() as ctx:
                page = await ctx.new_page()
                page.set_default_timeout(15_000)
                await self._rate_limit()
                await page.goto(career_url, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(1500)

                html = await page.content()
                soup = BeautifulSoup(html, "lxml")

                links = (
                    soup.select("div.ResJobListing a[href]")
                    or soup.select("li[data-id] a[href]")
                    or soup.select("[class*='JobListing'] a[href]")
                    or soup.select("[class*='job-listing'] a[href]")
                )
                results = _extract_jobs_from_soup_links(links, company_name, career_url, "bamboohr")

                await page.close()
                return [r for r in results if _is_se_role(r.job_title)]
        except Exception as exc:
            logger.warning("bamboohr_scrape_error", company=company_name, error=str(exc))
            return []

    # ── Tier 8: Enhanced generic Playwright + BS4 fallback ───────────────

    async def _scrape_playwright_enhanced(self, company_name: str, career_url: str) -> list[RawJob]:
        if not await self._can_fetch(career_url):
            logger.debug("robots_blocked", url=career_url)
            return []

        try:
            async with self._browser_session() as ctx:
                page = await ctx.new_page()
                page.set_default_timeout(15_000)
                await self._rate_limit()
                await page.goto(career_url, wait_until="domcontentloaded", timeout=20_000)
                await page.wait_for_timeout(2000)

                # Step 1: Try to find a search box and search for "software engineer"
                searched = False
                for sel in _SEARCH_BOX_SELECTORS:
                    el = await page.query_selector(sel)
                    if el:
                        try:
                            await el.fill("software engineer")
                            await el.press("Enter")
                            await page.wait_for_timeout(2500)
                            searched = True
                        except Exception:
                            pass
                        break

                if not searched:
                    # Try submit button near search inputs
                    btn = await page.query_selector(
                        "button[type='submit'][aria-label*='search' i], "
                        "button[class*='search' i][type='submit']"
                    )
                    if btn:
                        try:
                            await btn.click()
                            await page.wait_for_timeout(2000)
                        except Exception:
                            pass

                all_results: list[RawJob] = []

                for _page_num in range(5):  # scrape up to 5 pages
                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    # Multi-pattern extraction (first match wins)
                    page_links: list = []
                    for pattern in _GENERIC_CARD_PATTERNS:
                        try:
                            matches = soup.select(pattern)
                        except Exception:
                            continue
                        if matches:
                            page_links = matches
                            break

                    batch = _extract_jobs_from_soup_links(page_links, company_name, career_url)
                    all_results.extend(r for r in batch if _is_se_role(r.job_title))

                    # Try to go to next page
                    next_found = False
                    for next_sel in _NEXT_PAGE_SELECTORS:
                        next_btn = await page.query_selector(next_sel)
                        if next_btn:
                            try:
                                is_disabled = await next_btn.get_attribute("disabled")
                                if is_disabled:
                                    break
                                await next_btn.click()
                                await page.wait_for_timeout(2000)
                                next_found = True
                            except Exception:
                                pass
                            break
                    if not next_found:
                        break

                await page.close()
                logger.debug("playwright_enhanced_scrape", company=company_name, found=len(all_results))
                return all_results

        except Exception as exc:
            logger.warning("playwright_enhanced_error", company=company_name, error=str(exc))
            return []


# ── Module-level helpers ──────────────────────────────────────────────────────

def _extract_location(loc) -> Optional[str]:
    if isinstance(loc, list) and loc:
        first = loc[0]
        return first.get("name") or first.get("location") if isinstance(first, dict) else str(first)
    if isinstance(loc, dict):
        return loc.get("name") or loc.get("location")
    if isinstance(loc, str):
        return loc or None
    return None


def _lever_description(item: dict) -> str:
    parts: list[str] = []
    for section in (item.get("description", ""), item.get("descriptionPlain", "")):
        if section:
            parts.append(_strip_html(str(section)))
    for lst in item.get("lists", []):
        text = lst.get("text", "") + " " + lst.get("content", "")
        parts.append(_strip_html(text))
    return "\n\n".join(p for p in parts if p).strip()
