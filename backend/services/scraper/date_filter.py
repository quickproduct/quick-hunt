"""Centralized date parsing and freshness filtering for job scraping.

All date-format parsing logic lives here so every adapter and task can
share one canonical implementation instead of duplicating regexes.

Core rule: only accept jobs posted within the last *max_job_age_days*
days (default 60, i.e. current month + previous month).  Jobs whose
posted_date cannot be determined are **passed through** by default
(strict=False); set strict=True to reject them.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_MAX_AGE_DAYS = 60


@dataclass
class ScrapeDateStats:
    total_found: int = 0
    fresh_kept: int = 0
    old_skipped: int = 0
    date_unavailable: int = 0
    parse_failures: int = 0
    portal: str = ""

    def to_dict(self) -> dict:
        return {
            "portal": self.portal,
            "total_found": self.total_found,
            "fresh_kept": self.fresh_kept,
            "old_skipped": self.old_skipped,
            "date_unavailable": self.date_unavailable,
            "parse_failures": self.parse_failures,
        }


def parse_relative_date(text: str) -> Optional[datetime]:
    """Parse common relative/absolute date strings from job portals.

    Supported formats:
      - "Today", "Just now", "Just posted", "Posted recently", "Active today"
      - "Yesterday"
      - "N days ago", "N day ago"
      - "N hours ago", "N hour ago", "N hr ago", "N hrs ago"
      - "N weeks ago", "N week ago"
      - "N months ago", "N month ago"
      - "30+ days ago", "30+"
      - "Mar 12, 2026", "March 12, 2026"
      - "2026-03-12", "2026-03-12T10:30:00", "2026-03-12 10:30:00"
      - "12 Mar 2026", "12 March 2026"
      - RFC 2822 style (RSS feeds)

    Returns None if the text cannot be parsed.
    """
    if not text or not text.strip():
        return None

    raw = text.strip()
    low = raw.lower()

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # ── Exact keyword matches ────────────────────────────────────────────
    if low in ("today", "just now", "just posted", "posted recently",
               "active today", "recent", "posted today"):
        return now

    if low in ("yesterday",):
        return now - timedelta(days=1)

    # ── "30+ days ago" / "30+" ───────────────────────────────────────────
    if "30+" in low:
        return now - timedelta(days=31)

    # ── "N hours ago" ────────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*(?:hours?|hrs?|h)\s*ago", low)
    if m:
        return now - timedelta(hours=min(int(m.group(1)), 72))

    # ── "N days ago" ─────────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*(?:days?|d)\s*ago", low)
    if m:
        return now - timedelta(days=min(int(m.group(1)), 365))

    # ── "N weeks ago" ────────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*(?:weeks?|w)\s*ago", low)
    if m:
        return now - timedelta(weeks=min(int(m.group(1)), 52))

    # ── "N months ago" ───────────────────────────────────────────────────
    m = re.match(r"(\d+)\s*(?:months?|mo)\s*ago", low)
    if m:
        days = int(m.group(1)) * 30
        return now - timedelta(days=min(days, 365 * 5))

    # ── Bare "N days" / "N weeks" (some portals omit "ago") ─────────────
    m = re.match(r"(\d+)\s*days?$", low)
    if m:
        return now - timedelta(days=min(int(m.group(1)), 365))

    m = re.match(r"(\d+)\s*weeks?$", low)
    if m:
        return now - timedelta(weeks=min(int(m.group(1)), 52))

    # ── Absolute date formats ────────────────────────────────────────────

    # ISO: "2026-03-12 10:30:00", "2026-03-12T10:30:00", "2026-03-12"
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.split(".")[0].rstrip("Z"), fmt)
        except ValueError:
            continue

    # "Mar 12, 2026" / "March 12, 2026"
    m = re.match(
        r"([A-Z][a-z]{2,8})\.?\s+(\d{1,2}),?\s+(\d{4})", raw
    )
    if m:
        try:
            return datetime.strptime(
                f"{m.group(1)} {m.group(2)} {m.group(3)}", "%B %d %Y"
            )
        except ValueError:
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y"
                )
            except ValueError:
                pass

    # "12 Mar 2026" / "12 March 2026"
    m = re.match(
        r"(\d{1,2})\s+([A-Z][a-z]{2,8})\.?\s+(\d{4})", raw
    )
    if m:
        for fmt in ("%d %B %Y", "%d %b %Y"):
            try:
                return datetime.strptime(
                    f"{m.group(1)} {m.group(2)} {m.group(3)}", fmt
                )
            except ValueError:
                continue

    # RFC 2822 (RSS feeds): "Mon, 12 Mar 2026 10:30:00 +0000"
    from email.utils import parsedate_to_datetime
    try:
        dt = parsedate_to_datetime(raw)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        pass

    return None


def get_freshness_cutoff(max_age_days: int | None = None) -> datetime:
    """Return the datetime threshold: jobs posted *before* this are stale."""
    days = max_age_days if max_age_days is not None else _DEFAULT_MAX_AGE_DAYS
    return datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)


def is_job_fresh(
    posted_date: Optional[datetime],
    max_age_days: int | None = None,
    strict: bool = False,
) -> bool:
    """Check if a job's posted_date falls within the freshness window.

    Args:
        posted_date: The parsed date, or None if unavailable.
        max_age_days: Maximum age in days (default from config or 60).
        strict: If True, reject jobs with no posted_date.
                If False (default), pass them through.

    Returns:
        True if the job should be kept, False if it should be skipped.
    """
    if posted_date is None:
        return not strict

    cutoff = get_freshness_cutoff(max_age_days)

    # Handle timezone-aware datetimes by stripping tzinfo for comparison
    pd = posted_date
    if pd.tzinfo is not None:
        pd = pd.replace(tzinfo=None)

    return pd >= cutoff


def filter_jobs_by_freshness(
    jobs_data: list[dict],
    max_age_days: int | None = None,
    strict: bool = False,
    portal: str = "",
) -> tuple[list[dict], ScrapeDateStats]:
    """Filter a list of job dicts by posted_date freshness.

    Returns:
        (fresh_jobs, stats) tuple.
    """
    stats = ScrapeDateStats(portal=portal)
    stats.total_found = len(jobs_data)

    fresh: list[dict] = []

    for jd in jobs_data:
        pd = jd.get("posted_date")

        if pd is None:
            raw_pd = jd.get("raw_data", {}).get("posted_date_raw") if isinstance(jd.get("raw_data"), dict) else None
            if raw_pd and isinstance(raw_pd, str):
                pd = parse_relative_date(raw_pd)

        if pd is None:
            stats.date_unavailable += 1
            if is_job_fresh(None, max_age_days, strict):
                fresh.append(jd)
            else:
                stats.old_skipped += 1
            continue

        if isinstance(pd, str):
            parsed = parse_relative_date(pd)
            if parsed is None:
                stats.parse_failures += 1
                stats.date_unavailable += 1
                if is_job_fresh(None, max_age_days, strict):
                    fresh.append(jd)
                else:
                    stats.old_skipped += 1
                continue
            pd = parsed
            jd["posted_date"] = pd

        if is_job_fresh(pd, max_age_days, strict):
            fresh.append(jd)
            stats.fresh_kept += 1
        else:
            stats.old_skipped += 1

    return fresh, stats
