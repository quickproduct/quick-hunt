"""Shared placeholder/junk email detection for all job portals.

Single canonical source of truth — imported by:
  - services.scraper.tasks          (fix_placeholder_emails_task)
  - services.sender.tasks           (send skip guard)
  - services.api.routers.stats      (dashboard stats exclusion)
  - services.scraper.adapters.shine (jRE field guard)
"""

import re

# Exact placeholder emails returned by portal APIs instead of a real recruiter
# email. O(1) lookup via frozenset.
PLACEHOLDER_EMAILS: frozenset[str] = frozenset({
    "shinetest12345@gmail.com",  # Shine __NEXT_DATA__ jRE field default — 164 rows in DB
})

# Any email whose domain matches one of these is not a real HR contact.
PLACEHOLDER_DOMAINS: frozenset[str] = frozenset({
    # Indeed portal placeholders
    "in.indeed.com",
    "indeed.com",
    "indeedmail.com",
    # Disposable/temporary email services
    "wishtempuser.com",
})

# Role-based local-parts that are not real recruiter inboxes. These
# auto-respond, route to ticketing systems, or bounce — never use them as
# HR contacts.
ROLE_BASED_PREFIXES: frozenset[str] = frozenset({
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "info", "support", "hello", "contact", "admin",
    "webmaster", "postmaster", "abuse", "marketing",
    "sales", "billing", "help", "feedback", "office",
})

# Catches any email whose "domain" part ends with an image or CSS file
# extension. None of these are valid DNS TLDs, so false-positive risk is zero.
_IMAGE_DOMAIN_RE = re.compile(
    r"\.(?:png|jpe?g|gif|svg|webp|avif|css|js)$",
    re.IGNORECASE,
)


def is_placeholder_email(email: str | None) -> bool:
    """Return True if email is a placeholder, junk, or not a real HR contact.

    Checks (in order):
    1. Exact match against PLACEHOLDER_EMAILS
    2. Domain match against PLACEHOLDER_DOMAINS
    3. Regex match for image/CSS filename patterns
    4. Role-based local-part (noreply@, info@, support@, etc.)
    """
    if not email:
        return False
    email_lower = email.lower().strip()

    if email_lower in PLACEHOLDER_EMAILS:
        return True

    if "@" not in email_lower:
        return False
    local, domain = email_lower.rsplit("@", 1)

    if domain in PLACEHOLDER_DOMAINS:
        return True

    if _IMAGE_DOMAIN_RE.search(email_lower):
        return True

    if local in ROLE_BASED_PREFIXES:
        return True

    return False
