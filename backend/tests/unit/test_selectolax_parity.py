"""Parity tests: services.scraper.html (selectolax) vs bs4+lxml.

These assert the selectolax-backed wrapper returns identical results to
BeautifulSoup for the exact selector operations the migrated adapters run
(indeed, internshala, shine, jobspresso, the HR-email link discovery). This is
the regression guard for the lxml/bs4 -> selectolax swap.
"""
import json

import pytest
from bs4 import BeautifulSoup as BS4

from services.scraper.html import BeautifulSoup as SLX


def _lines(text: str) -> list[str]:
    """Non-empty, stripped lines — normalizes whitespace differences between
    the two parsers so we compare logical content, not exact spacing."""
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


# --- Indeed list card -----------------------------------------------------
INDEED_CARD = """
<html><body>
<div class="job_seen_beacon">
  <h2 class="jobTitle"><a href="/rc/clk?jk=abc123&bb=xyz">Senior PHP Developer</a></h2>
  <span class="companyName">Acme Corp</span>
  <div class="companyLocation">Bengaluru, KA</div>
  <span class="date">Posted 2 days ago</span>
</div>
<div class="job_seen_beacon">
  <h2 class="jobTitle"><a href="/rc/clk?jk=def456">Laravel Engineer</a></h2>
  <span data-testid="company-name">Globex</span>
  <div data-testid="text-location">Remote</div>
</div>
</body></html>
"""


def test_indeed_card_selection_parity():
    bs, slx = BS4(INDEED_CARD, "lxml"), SLX(INDEED_CARD, "lxml")
    assert len(bs.select("div.job_seen_beacon")) == len(slx.select("div.job_seen_beacon")) == 2

    for b_card, s_card in zip(bs.select("div.job_seen_beacon"), slx.select("div.job_seen_beacon")):
        bt, st = b_card.select_one("h2.jobTitle a"), s_card.select_one("h2.jobTitle a")
        assert bt.get_text(strip=True) == st.get_text(strip=True)
        assert bt.get("href", "") == st.get("href", "")

    # data-testid attribute selector + substring fallback used by indeed
    assert (
        bs.select_one("[data-testid='company-name']").get_text(strip=True)
        == slx.select_one("[data-testid='company-name']").get_text(strip=True)
        == "Globex"
    )


# --- Indeed detail --------------------------------------------------------
INDEED_DETAIL = """
<html><body>
<h1 class="jobsearch-JobInfoHeader-title">Backend Engineer</h1>
<div class="jobsearch-CompanyInfoContainer"><a href="https://acme.example.com">Acme Corp</a></div>
<div id="jobDescriptionText">
  <p>We are hiring.</p>
  <p>Email careers@acme.example.com to apply.</p>
  <ul><li>PHP</li><li>Laravel</li></ul>
</div>
</body></html>
"""


def test_indeed_detail_parity():
    bs, slx = BS4(INDEED_DETAIL, "lxml"), SLX(INDEED_DETAIL, "lxml")
    assert (
        bs.select_one("h1.jobsearch-JobInfoHeader-title").get_text(strip=True)
        == slx.select_one("h1.jobsearch-JobInfoHeader-title").get_text(strip=True)
    )
    bc = bs.select_one("div.jobsearch-CompanyInfoContainer a")
    sc = slx.select_one("div.jobsearch-CompanyInfoContainer a")
    assert bc.get_text(strip=True) == sc.get_text(strip=True)
    assert bc.get("href", "") == sc.get("href", "")

    bd = bs.select_one("div#jobDescriptionText").get_text(separator="\n", strip=True)
    sd = slx.select_one("div#jobDescriptionText").get_text(separator="\n", strip=True)
    assert _lines(bd) == _lines(sd)
    # the description text must still yield the same extractable email
    assert "careers@acme.example.com" in sd


# --- Internshala (substring class selectors) ------------------------------
INTERNSHALA = """
<html><body>
<div class="individual_internship">
  <h3 class="job-internship-name"><a href="/jobs/detail/dev-123">Web Developer</a></h3>
  <div class="company_name"><a href="https://co.example.com">Startup Inc</a></div>
  <div class="location_link">Mumbai</div>
</div>
<div class="internship_details">
  <div class="text-container">Build  features.\nContact hr@startup.example.com</div>
</div>
</body></html>
"""


def test_internshala_substring_and_text_parity():
    bs, slx = BS4(INTERNSHALA, "lxml"), SLX(INTERNSHALA, "lxml")
    # substring attribute selector
    assert len(bs.select("div[class*='internship']")) == len(slx.select("div[class*='internship']"))
    bt = bs.select_one("h3.job-internship-name a")
    st = slx.select_one("h3.job-internship-name a")
    assert bt.get_text(strip=True) == st.get_text(strip=True)
    assert bt.get("href", "") == st.get("href", "")

    bdesc = bs.select_one("div.internship_details div.text-container").get_text(separator="\n", strip=True)
    sdesc = slx.select_one("div.internship_details div.text-container").get_text(separator="\n", strip=True)
    assert _lines(bdesc) == _lines(sdesc)


# --- shine: find(script, id=...) + get_text -> json -----------------------
SHINE_NEXT = (
    '<html><body><script id="__NEXT_DATA__" type="application/json">'
    + json.dumps({"props": {"pageProps": {"x": 1}}})
    + "</script></body></html>"
)


def test_find_script_by_id_parity():
    bs, slx = BS4(SHINE_NEXT, "lxml"), SLX(SHINE_NEXT, "lxml")
    bn = bs.find("script", id="__NEXT_DATA__")
    sn = slx.find("script", id="__NEXT_DATA__")
    assert bn is not None and sn is not None
    assert json.loads(bn.get_text()) == json.loads(sn.get_text())


# --- HR-email link discovery: find_all("a", href=True) --------------------
LINKS = """
<html><body>
<a href="/about">About</a>
<a>no href</a>
<a href="https://x.example.com/careers">Careers</a>
<a href="mailto:hr@x.example.com">Mail</a>
</body></html>
"""


def test_find_all_anchors_with_href_parity():
    bs, slx = BS4(LINKS, "lxml"), SLX(LINKS, "lxml")
    b_hrefs = [a["href"] for a in bs.find_all("a", href=True)]
    s_hrefs = [a["href"] for a in slx.find_all("a", href=True)]
    assert b_hrefs == s_hrefs
    assert "/about" in s_hrefs and "mailto:hr@x.example.com" in s_hrefs
