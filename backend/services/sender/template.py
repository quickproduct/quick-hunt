"""HTML and plain-text email template renderer."""
import re
from typing import Any

# Matches "Sincerely," / "Best regards," / "Regards," and everything that follows
# (including the candidate name line). Strip it so we can add a consistent block.
_SIGNATURE_RE = re.compile(
    r"\n\s*(sincerely|best regards?|regards?|best|yours? (?:truly|sincerely)?|thanking you)[,.]?.*$",
    re.IGNORECASE | re.DOTALL,
)


def _strip_signature(text: str) -> str:
    """Remove trailing signature block from cover letter text."""
    return _SIGNATURE_RE.sub("", text).rstrip()


_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _markdown_bold_to_html(text: str) -> str:
    """Convert ``**text**`` markdown bold to ``<strong>text</strong>``."""
    return _BOLD_RE.sub(r"<strong>\1</strong>", text)


def _strip_markdown_bold(text: str) -> str:
    """Remove ``**`` markers from plain-text output."""
    return _BOLD_RE.sub(r"\1", text)


def _cover_to_paragraphs_html(cover_letter: str) -> str:
    """Convert multiline cover letter text into HTML paragraphs."""
    paragraphs = [p.strip() for p in cover_letter.strip().split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [cover_letter.strip()]
    return "\n".join(
        f"<p>{_markdown_bold_to_html(p.replace(chr(10), '<br>'))}</p>"
        for p in paragraphs
    )


def render_html(cover_letter: str, candidate: Any, job: Any) -> str:
    """Render full HTML email body."""
    candidate_name = getattr(candidate, "name", "Candidate")
    body_text = _strip_signature(cover_letter)
    cover_html = _cover_to_paragraphs_html(body_text)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{ font-family: Georgia, 'Times New Roman', serif; color: #222; max-width: 680px; margin: 0 auto; padding: 24px; line-height: 1.7; }}
    p {{ margin: 0 0 1em 0; }}
    .signature {{ margin-top: 1.5em; }}
  </style>
</head>
<body>
  {cover_html}
  <div class="signature">
    Sincerely,<br>
    {candidate_name}
  </div>
</body>
</html>"""


def render_plain(cover_letter: str, candidate: Any, job: Any) -> str:
    """Render plain-text email body."""
    candidate_name = getattr(candidate, "name", "Candidate")
    body_text = _strip_signature(cover_letter)
    return f"{_strip_markdown_bold(body_text)}\n\nSincerely,\n{candidate_name}"
