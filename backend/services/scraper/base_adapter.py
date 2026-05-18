"""Base scraper adapter — all portal adapters inherit from BaseAdapter."""
import asyncio
import hashlib
import random
import re
import urllib.robotparser
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import httpx
import structlog

from services.api.core.config import get_settings

logger = structlog.get_logger(__name__)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", re.IGNORECASE)
SKIP_DOMAINS = {
    "example.com", "noreply.com", "naukri.com", "indeed.com", "in.indeed.com",
    "glassdoor.com", "linkedin.com", "monster.com", "dice.com",
    "sentry.io", "amazonaws.com", "w3.org", "schema.org",
}

# Image filename suffixes that get mistaken for emails (e.g. "logo@2x.png")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp"}
# Retina image scale suffixes (e.g. "@2x", "@3x") that appear before the extension
_RETINA_RE = re.compile(r"@\d+x$", re.IGNORECASE)
# Sentry/tracking IDs: 32-char hex local-part (e.g. "995b2433a7014c708e4dcc34f1893550@sentry.wrike.com")
_HEX_LOCAL_RE = re.compile(r"^[0-9a-f]{32,}$", re.IGNORECASE)
# Domain ends with an image/CSS extension — catches cases where the "@2x-HASH.ext"
# part becomes the "domain" after splitting on "@" (e.g. ladder@2x-434b82.webp)
_IMAGE_DOMAIN_RE = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|avif|css|js)$",
    re.IGNORECASE,
)


def _is_junk_email(email: str) -> bool:
    """Return True if the string looks like an image filename, Sentry ID, etc."""
    local, domain = email.rsplit("@", 1)
    local_lower = local.lower()
    domain_lower = domain.lower()

    # Retina image suffixes: logo@2x.png → local="logo", but the full match
    # would be "logo@2x" — check if local ends with a retina scale token
    if _RETINA_RE.search(local_lower):
        return True

    # Image file extension in local part (e.g. "icon@2x.png" matched as local="icon@2x.png"
    # won't happen with the regex, but "Demo-Img@2x.png" → local contains ".png")
    for ext in _IMAGE_EXTENSIONS:
        if local_lower.endswith(ext):
            return True

    # Sentry / tracking hash: 32+ hex chars
    if _HEX_LOCAL_RE.match(local_lower):
        return True

    # Sentry subdomain on any host (e.g. sentry.wrike.com)
    if "sentry." in domain_lower or domain_lower.startswith("sentry"):
        return True

    # Domain looks like an image/CSS filename — catches retina patterns where
    # the @2x-HASH.ext part becomes the domain after splitting on @
    if _IMAGE_DOMAIN_RE.search(domain_lower):
        return True

    return False


@dataclass
class JobQuery:
    job_title: str
    location: str
    max_results: int = 50
    candidate_id: Optional[str] = None
    auto_generate_covers: bool = False
    auto_send: bool = False


@dataclass
class RawJob:
    job_title: str
    company: str
    job_url: str
    source_portal: str
    location: Optional[str] = None
    job_description: Optional[str] = None
    posted_date: Optional[datetime] = None
    hr_email: Optional[str] = None
    company_website: Optional[str] = None
    recruiter_name: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: Optional[str] = None
    job_type: Optional[str] = None
    experience_required: Optional[str] = None
    raw_data: dict = field(default_factory=dict)
    dedupe_hash: str = field(default="")

    def __post_init__(self) -> None:
        if not self.dedupe_hash:
            self.dedupe_hash = compute_dedupe_hash(self.job_url, self.job_title, self.company)


def _normalize_job_url(url: str) -> str:
    """Strip tracking/session params so the same job always produces the same URL.

    Indeed rotates `bb=` on every crawl; LinkedIn adds `refId=` and `trackingId=`.
    We keep only the canonical job-ID param (`jk=` for Indeed) or the path
    (for LinkedIn /jobs/view/<id>), discarding everything else.
    """
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

    if not url:
        return url
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=False)

    # Indeed: keep only `jk` (the stable job key)
    if "indeed.com" in parsed.netloc:
        stable_qs = {k: v for k, v in qs.items() if k == "jk"}
        return urlunparse(parsed._replace(query=urlencode(stable_qs, doseq=True), fragment=""))

    # LinkedIn: path already contains the stable numeric job ID — drop all query params
    if "linkedin.com" in parsed.netloc:
        # Strip trailing slashes and any query/fragment
        path = parsed.path.rstrip("/")
        return urlunparse(parsed._replace(path=path, query="", fragment=""))

    # Generic: drop known tracking params, keep everything else
    _TRACKING = {"bb", "refId", "trackingId", "utm_source", "utm_medium",
                 "utm_campaign", "utm_term", "utm_content"}
    stable_qs = {k: v for k, v in qs.items() if k not in _TRACKING}
    return urlunparse(parsed._replace(query=urlencode(stable_qs, doseq=True), fragment=""))


def compute_dedupe_hash(job_url: str, job_title: str, company: str) -> str:
    """Stable SHA-256 hash for deduplication — case-insensitive, URL-normalized.

    URL is normalized before hashing so that the same job scraped on different
    days (with rotated Indeed `bb=` tokens or LinkedIn `refId=` params) produces
    the same hash and is not re-inserted as a new job.
    """
    normalized_url = _normalize_job_url(job_url or "")
    key = f"{normalized_url}:{job_title.lower().strip()}:{company.lower().strip()}"
    return hashlib.sha256(key.encode()).hexdigest()


def extract_emails_from_text(text: str) -> list[str]:
    """Extract valid, non-portal email addresses from arbitrary text."""
    from services.common.placeholder_emails import PLACEHOLDER_EMAILS

    found = EMAIL_RE.findall(text or "")
    result = []
    seen: set[str] = set()
    for email in found:
        domain = email.split("@")[-1].lower()
        if domain in SKIP_DOMAINS:
            continue
        if _is_junk_email(email):
            continue
        if email.lower() in PLACEHOLDER_EMAILS:
            continue
        email_lower = email.lower()
        if email_lower not in seen:
            seen.add(email_lower)
            result.append(email)
    return result


class BaseAdapter(ABC):
    """Abstract base class for all job portal scrapers."""

    PORTAL_NAME: str = "base"
    REQUESTS_PER_MINUTE: int = 10
    CONCURRENT_BROWSERS: int = 1

    def __init__(self) -> None:
        self._request_times: list[float] = []
        self._robots_cache: dict[str, tuple[urllib.robotparser.RobotFileParser | None, float]] = {}
        self._settings = get_settings()
        self._shared_context = None  # set by _browser_session()
        self._page_counter = 0
        self._consecutive_nav_failures = 0
        self._MAX_CONSECUTIVE_FAILURES = 5
        self._robots_cache_ttl = 3600  # 1 hour TTL for robots.txt cache

    # ------------------------------------------------------------------ #
    # Rate limiting                                                        #
    # ------------------------------------------------------------------ #
    async def _rate_limit(self) -> None:
        """Enforce REQUESTS_PER_MINUTE. Adds extra wait only when near the limit."""
        loop = asyncio.get_running_loop()
        now = loop.time()
        self._request_times = [t for t in self._request_times if now - t < 60]
        if len(self._request_times) >= self.REQUESTS_PER_MINUTE:
            sleep = 60 - (now - self._request_times[0]) + random.uniform(0.5, 1.5)
            await asyncio.sleep(max(sleep, 0))
        self._request_times.append(loop.time())
        # Polite crawl delay (configurable, default 2.0s with ±25% jitter)
        delay = self._settings.default_crawl_delay_seconds
        await asyncio.sleep(delay * random.uniform(0.75, 1.25))

    # ------------------------------------------------------------------ #
    # robots.txt                                                           #
    # ------------------------------------------------------------------ #
    async def _can_fetch(self, url: str) -> bool:
        """Check robots.txt. Returns True if allowed (fail open)."""
        if not self._settings.respect_robots_txt:
            return True
        parsed = urlparse(url)
        domain = f"{parsed.scheme}://{parsed.netloc}"
        import time as _time
        now = _time.monotonic()
        if domain in self._robots_cache:
            cached_rp, cached_at = self._robots_cache[domain]
            if now - cached_at > self._robots_cache_ttl:
                del self._robots_cache[domain]
            elif cached_rp is None:
                return True
            else:
                return cached_rp.can_fetch("*", url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{domain}/robots.txt")
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, rp.read)
        except Exception:
            self._robots_cache[domain] = (None, now)
            return True
        self._robots_cache[domain] = (rp, now)
        return rp.can_fetch("*", url)

    # ------------------------------------------------------------------ #
    # Playwright browser session — reuse across multiple page fetches     #
    # ------------------------------------------------------------------ #
    @asynccontextmanager
    async def _browser_session(self):
        """Create a shared browser context for the duration of a scraping session.

        While inside this context, _get_page_html opens new tabs in the existing
        browser instead of launching a fresh browser per page — a major speedup.
        """
        from playwright.async_api import async_playwright  # lazy import

        settings = self._settings
        proxy = {"server": settings.proxy_url} if settings.proxy_url else None

        _LAUNCH_ARGS = [
            "--no-sandbox",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-setuid-sandbox",
            "--no-zygote",
            "--single-process",
            "--disable-software-rasterizer",
        ]

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=_LAUNCH_ARGS)
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="Asia/Kolkata",
                proxy=proxy,
            )
            self._shared_context = ctx
            try:
                yield ctx
            finally:
                self._shared_context = None
                await browser.close()

    # ------------------------------------------------------------------ #
    # Playwright page fetcher                                              #
    # ------------------------------------------------------------------ #
    # Navigation timeout (ms) — 45s per attempt (increased from 30s for slower portals).
    _NAV_TIMEOUT = 45_000
    # Maximum number of retries for navigation timeouts / page crashes.
    _NAV_RETRIES = 3
    # Recreate browser context after this many pages to prevent memory leaks.
    _PAGES_PER_CONTEXT = 10

    async def _navigate_with_retry(self, page, url: str, wait_selector: Optional[str] = None) -> str:
        """Navigate to *url* with retries on timeout or page crash. Returns page HTML."""
        if self._consecutive_nav_failures >= self._MAX_CONSECUTIVE_FAILURES:
            raise RuntimeError(
                f"Aborting: {self._consecutive_nav_failures} consecutive navigation failures"
            )

        last_exc: Exception | None = None
        for attempt in range(1, self._NAV_RETRIES + 1):
            try:
                if page.is_closed():
                    if self._shared_context is not None:
                        page = await self._shared_context.new_page()
                    else:
                        raise last_exc or RuntimeError(f"Page closed and no shared context for {url}")

                await page.goto(url, wait_until="domcontentloaded", timeout=self._NAV_TIMEOUT)
                if wait_selector:
                    try:
                        await page.wait_for_selector(wait_selector, timeout=15000)
                    except Exception:
                        pass
                self._consecutive_nav_failures = 0
                self._page_counter += 1
                return await page.content()
            except Exception as exc:
                last_exc = exc
                self._consecutive_nav_failures += 1
                if attempt < self._NAV_RETRIES:
                    logger.warning(
                        "page_nav_retry",
                        url=url,
                        attempt=attempt,
                        error=str(exc)[:200],
                    )
                    await asyncio.sleep(2 ** attempt)
        raise last_exc or RuntimeError(f"All navigation retries exhausted for {url}")

    async def _get_page_html(self, url: str, wait_selector: Optional[str] = None) -> str:
        """Navigate to URL and return HTML. Reuses the shared browser context when available."""
        if self._shared_context is not None:
            page = await self._shared_context.new_page()
            try:
                html = await self._navigate_with_retry(page, url, wait_selector)
                if self._page_counter >= self._PAGES_PER_CONTEXT:
                    logger.info(
                        "browser_context_recycling",
                        pages=self._page_counter,
                        portal=self.PORTAL_NAME,
                    )
                    self._page_counter = 0
                    try:
                        await self._shared_context.close()
                        browser = self._shared_context.browser
                        if browser:
                            recycle_proxy = {"server": self._settings.proxy_url} if self._settings.proxy_url else None
                            ctx = await browser.new_context(
                                user_agent=(
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/124.0.0.0 Safari/537.36"
                                ),
                                viewport={"width": 1280, "height": 900},
                                locale="en-US",
                                timezone_id="Asia/Kolkata",
                                proxy=recycle_proxy,
                            )
                            self._shared_context = ctx
                    except Exception as exc:
                        logger.warning("context_recycle_failed", error=str(exc)[:200])
                return html
            finally:
                if not page.is_closed():
                    await page.close()

        # Fallback: create a fresh browser for single-page fetches (e.g. parse_job_detail)
        from playwright.async_api import async_playwright  # lazy import

        settings = self._settings
        proxy = {"server": settings.proxy_url} if settings.proxy_url else None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-setuid-sandbox",
                    "--no-zygote",
                    "--single-process",
                    "--disable-software-rasterizer",
                ],
            )
            ctx = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="en-US",
                timezone_id="Asia/Kolkata",
                proxy=proxy,
            )
            page = await ctx.new_page()
            try:
                html = await self._navigate_with_retry(page, url, wait_selector)
            finally:
                await browser.close()
        return html

    # ------------------------------------------------------------------ #
    # Email discovery                                                      #
    # ------------------------------------------------------------------ #
    async def _find_email_from_company_site(self, website: str) -> Optional[str]:
        """Crawl /contact /about /careers /team pages for HR email."""
        if not website:
            return None
        parsed = urlparse(website)
        base = f"{parsed.scheme}://{parsed.netloc}"
        pages_to_check = [website, f"{base}/contact", f"{base}/about", f"{base}/careers", f"{base}/team"]
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            for page_url in pages_to_check:
                try:
                    resp = await client.get(page_url)
                    if resp.status_code == 200:
                        emails = extract_emails_from_text(resp.text)
                        hr_keywords = ["hr@", "recruit", "talent", "hiring", "careers@", "jobs@", "people@"]
                        for email in emails:
                            if any(kw in email.lower() for kw in hr_keywords):
                                return email
                        if emails:
                            return emails[0]
                except Exception:
                    continue
        return None

    # ------------------------------------------------------------------ #
    # Abstract interface                                                   #
    # ------------------------------------------------------------------ #
    @abstractmethod
    async def search_jobs(self, query: JobQuery) -> list[RawJob]:
        """Search portal for jobs matching query. Returns list of RawJob."""
        ...

    @abstractmethod
    async def parse_job_detail(self, url: str) -> Optional[RawJob]:
        """Fetch full job detail page and return enriched RawJob."""
        ...

    async def find_hr_email(self, job: RawJob) -> Optional[str]:
        """Attempt to discover HR/recruiter email for the job."""
        # 1. Extract from job description
        if job.job_description:
            emails = extract_emails_from_text(job.job_description)
            if emails:
                return emails[0]

        # 2. Crawl company website
        if job.company_website:
            email = await self._find_email_from_company_site(job.company_website)
            if email:
                return email

        return None
