"""Unit tests for HTML parsing, email extraction, salary/date parsing, deduplication."""
from datetime import datetime, timedelta, timezone

import pytest

from services.scraper.base_adapter import (
    RawJob,
    compute_dedupe_hash,
    extract_emails_from_text,
)
from services.scraper.adapters.naukri import NaukriAdapter
from services.scraper.adapters.indeed import IndeedAdapter
from services.sender.template import render_html, render_plain


# ------------------------------------------------------------------ #
# Sample HTML fixtures                                                 #
# ------------------------------------------------------------------ #

SAMPLE_INDEED_CARD_HTML = """
<div class="job_seen_beacon">
  <h2 class="jobTitle">
    <a href="/rc/clk?jk=abc123">
      <span>Backend Developer</span>
    </a>
  </h2>
  <span class="companyName">AcmeCorp</span>
  <div class="companyLocation">Mumbai, Maharashtra</div>
  <div class="metadata salary-snippet-container">₹8,00,000 - ₹12,00,000 a year</div>
  <span class="date">2 days ago</span>
</div>
"""


# ------------------------------------------------------------------ #
# Email extraction tests                                               #
# ------------------------------------------------------------------ #

def test_extract_emails_basic():
    text = "Contact us at hr@company.com for applications"
    result = extract_emails_from_text(text)
    assert "hr@company.com" in result


def test_extract_emails_multiple():
    text = "Email hr@company.com or recruiter@startup.io"
    result = extract_emails_from_text(text)
    assert len(result) == 2
    assert "hr@company.com" in result
    assert "recruiter@startup.io" in result


def test_extract_emails_filters_portal_domains():
    text = "Apply at support@naukri.com or help@indeed.com"
    result = extract_emails_from_text(text)
    assert len(result) == 0


def test_extract_emails_filters_example_domains():
    text = "Do not email test@example.com"
    result = extract_emails_from_text(text)
    assert len(result) == 0


def test_extract_emails_empty_text():
    result = extract_emails_from_text("")
    assert result == []


# ------------------------------------------------------------------ #
# Deduplication hash tests                                             #
# ------------------------------------------------------------------ #

def test_rawjob_dedupe_hash_stable():
    h1 = compute_dedupe_hash("https://naukri.com/job/123", "Senior Engineer", "TechCorp")
    h2 = compute_dedupe_hash("https://naukri.com/job/123", "Senior Engineer", "TechCorp")
    assert h1 == h2
    assert len(h1) == 64


def test_rawjob_dedupe_hash_different_for_different_jobs():
    h1 = compute_dedupe_hash("https://naukri.com/job/123", "Senior Engineer", "TechCorp")
    h2 = compute_dedupe_hash("https://naukri.com/job/456", "Junior Engineer", "OtherCorp")
    assert h1 != h2


def test_rawjob_dedupe_hash_case_insensitive():
    h1 = compute_dedupe_hash("https://naukri.com/job/123", "senior engineer", "techcorp")
    h2 = compute_dedupe_hash("https://naukri.com/job/123", "SENIOR ENGINEER", "TECHCORP")
    assert h1 == h2


# ------------------------------------------------------------------ #
# Naukri salary parsing                                                #
# ------------------------------------------------------------------ #

def test_naukri_salary_parse_lacs():
    sal_min, sal_max, currency = NaukriAdapter._parse_salary("8", "15")
    assert sal_min == 800000.0
    assert sal_max == 1500000.0
    assert currency == "INR"


def test_naukri_salary_parse_not_disclosed():
    sal_min, sal_max, currency = NaukriAdapter._parse_salary(None, None)
    assert sal_min is None
    assert sal_max is None
    assert currency is None


def test_naukri_salary_parse_single_value():
    sal_min, sal_max, currency = NaukriAdapter._parse_salary("10", "10")
    assert sal_min == 1000000.0
    assert sal_max == 1000000.0
    assert currency == "INR"


# ------------------------------------------------------------------ #
# Naukri date parsing                                                  #
# ------------------------------------------------------------------ #

def test_naukri_date_today():
    result = NaukriAdapter._parse_date("Today")
    assert result is not None
    assert (datetime.now(timezone.utc) - result).seconds < 60


def test_naukri_date_days_ago():
    result = NaukriAdapter._parse_date("3 Days Ago")
    assert result is not None
    expected = datetime.now(timezone.utc) - timedelta(days=3)
    assert abs((result - expected).total_seconds()) < 5


def test_naukri_date_weeks_ago():
    result = NaukriAdapter._parse_date("2 Weeks Ago")
    assert result is not None
    expected = datetime.now(timezone.utc) - timedelta(weeks=2)
    assert abs((result - expected).total_seconds()) < 5


# ------------------------------------------------------------------ #
# Naukri item parsing (uses _parse_item, not _parse_job_card)          #
# ------------------------------------------------------------------ #

def test_naukri_parse_item():
    item = {
        "title": "Senior Python Engineer",
        "companyName": "TechCorp Solutions",
        "location": "Bangalore",
        "salary": "12-18 Lacs PA",
        "experience": "3-6 Yrs",
        "job_url": "https://www.naukri.com/job/senior-python-engineer-12345",
    }
    adapter = NaukriAdapter()
    job = adapter._parse_item(item)
    assert job is not None
    assert job.job_title == "Senior Python Engineer"
    assert job.company == "TechCorp Solutions"
    assert job.location == "Bangalore"


# ------------------------------------------------------------------ #
# Indeed card parsing                                                  #
# ------------------------------------------------------------------ #

def test_indeed_parse_job_card():
    from bs4 import BeautifulSoup
    adapter = IndeedAdapter()
    soup = BeautifulSoup(SAMPLE_INDEED_CARD_HTML, "lxml")
    card = soup.select_one("div.job_seen_beacon")
    job = adapter._parse_job_card(card)
    assert job is not None
    assert job.company == "AcmeCorp"
    assert job.location == "Mumbai, Maharashtra"


def test_indeed_date_parse_days():
    result = IndeedAdapter._parse_date("2 days ago")
    assert result is not None
    expected = datetime.now(timezone.utc) - timedelta(days=2)
    assert abs((result - expected).total_seconds()) < 5


def test_indeed_date_parse_today():
    result = IndeedAdapter._parse_date("Today")
    assert result is not None
    assert (datetime.now(timezone.utc) - result).seconds < 60


# ------------------------------------------------------------------ #
# Email template rendering                                             #
# ------------------------------------------------------------------ #

class _FakeCandidate:
    name = "Jane Smith"
    skills = ["Python", "FastAPI"]
    years_experience = 4
    bio = "Backend developer"


class _FakeJob:
    job_title = "Senior Python Engineer"
    company = "TechCorp"
    location = "Bangalore"
    cover_letter = "Para one.\n\nPara two.\n\nPara three."


def test_render_email_html():
    html = render_html(_FakeJob.cover_letter, _FakeCandidate(), _FakeJob())
    assert "<html" in html
    assert "Para one" in html
    assert "Jane Smith" in html


def test_render_email_plain_text():
    plain = render_plain(_FakeJob.cover_letter, _FakeCandidate(), _FakeJob())
    assert "Para one" in plain
    assert "Jane Smith" in plain
    assert "<html" not in plain
