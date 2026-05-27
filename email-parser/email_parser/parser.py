"""LinkedIn job alert email parser — stdlib only, no third-party deps."""

import html as html_lib
import re
from typing import Optional

# <a href="...linkedin.com/jobs/view/ID...">TITLE</a>
# Captures: (full_url, job_id, inner_html)
_ANCHOR_JOB_RE = re.compile(
    r'<a\b[^>]+href=["\']'
    r'(https://www\.linkedin\.com/(?:comm/)?jobs/view/(\d+)[^"\']*)'
    r'["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)

# Fallback: bare URL not inside an <a> tag
_BARE_JOB_RE = re.compile(r"https://www\.linkedin\.com/(?:comm/)?jobs/view/(\d+)")

# First block-level element right after an anchor — contains "Company · Location"
_FIRST_BLOCK_RE = re.compile(
    r"<(?:span|p|td|div|li)\b[^>]*>(.*?)</(?:span|p|td|div|li)>",
    re.IGNORECASE | re.DOTALL,
)

# Company after "at" keyword: "at BigCo"
_AT_COMPANY_RE = re.compile(r"\bat\s+([A-Z][A-Za-z0-9 &,.'!-]{2,60}?)(?:\s*[·•\n]|[,.]|$)")

# Window-based title: seniority keyword → separator
_WINDOW_TITLE_RE = re.compile(
    r"\b((?:Principal|Staff|Distinguished|Senior|Sr\.|Lead|Architect"
    r"|Director|VP|Vice\s+President|Head)[^·|<\n]{5,80}?)(?:\s*[·|]|\s+at\s)",
    re.IGNORECASE,
)

# Anchor texts that are navigation links, not job titles
_SKIP_TEXTS = frozenset(
    {
        "view job",
        "view",
        "apply",
        "apply now",
        "see more",
        "learn more",
        "click here",
        "more jobs like this",
        "unsubscribe",
        "manage alerts",
        "settings",
        "privacy policy",
        "help center",
    }
)

DEFAULT_SENIORITY_KEYWORDS: list[str] = [
    "principal",
    "staff",
    "distinguished",
    "senior",
    "sr.",
    "sr ",
    "lead",
    "architect",
    "director",
    "vp",
    "vice president",
    "head of",
    "head,",
]


def _strip_tags(text: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html_lib.unescape(text)).strip()


def _find_company(context: str) -> str:
    """Extract the company name from text that follows a job title anchor.

    LinkedIn alert emails use the pattern "Company · City, Province · Remote",
    so splitting on '·' and taking the first non-empty segment is the most
    robust approach — it handles special chars like '!' in company names.
    """
    context = context.strip()
    if not context:
        return "Unknown Company"

    parts = [p.strip() for p in context.split("·")]

    # Common case: company is the first segment before '·'
    first = parts[0]
    if first:
        if first.lower().startswith("at "):
            first = first[3:].strip()
        if first and first[0].isupper() and 2 <= len(first) <= 70:
            return first

    # Separator-first ("· Company · …"): check subsequent segments
    for part in parts[1:]:
        if part and part[0].isupper() and 2 <= len(part) <= 70:
            return part

    # Plain-text fallback: "at BigCo"
    m = _AT_COMPANY_RE.search(context)
    if m:
        return m.group(1).strip()

    return "Unknown Company"


def _context_after_anchor(html_body: str, anchor_end: int) -> str:
    """Return stripped text of the first block element after an anchor tag.

    Limiting to one block element prevents context from bleeding into the
    next job card when multiple cards appear in the same email.
    """
    after_raw = html_body[anchor_end : anchor_end + 600]
    block_m = _FIRST_BLOCK_RE.search(after_raw)
    if block_m:
        return _strip_tags(block_m.group(1))
    # No block element — take up to 200 chars, stopping at the next job URL
    next_url_m = _BARE_JOB_RE.search(after_raw)
    cutoff = next_url_m.start() if next_url_m else 200
    return _strip_tags(after_raw[:cutoff])


def parse(html_body: str) -> list[dict]:
    """Extract job postings from a LinkedIn job alert HTML email body.

    Returns a list of dicts with keys: title, company, url.
    """
    jobs: list[dict] = []
    seen_ids: set[str] = set()

    # Primary pass: job title IS the anchor text for job-URL links
    for m in _ANCHOR_JOB_RE.finditer(html_body):
        job_id = m.group(2)
        if job_id in seen_ids:
            continue

        title = _strip_tags(m.group(3)).strip()
        if not title or title.lower() in _SKIP_TEXTS or len(title) < 4:
            continue

        seen_ids.add(job_id)
        url = f"https://www.linkedin.com/jobs/view/{job_id}"
        after = _context_after_anchor(html_body, m.end())
        company = _find_company(after)

        jobs.append({"title": title, "company": company, "url": url})

    # Fallback: catch any job IDs not found via anchor tags (plain-text URLs)
    for m in _BARE_JOB_RE.finditer(html_body):
        job_id = m.group(1)
        if job_id in seen_ids:
            continue
        seen_ids.add(job_id)

        # Use a wide window of surrounding text
        start = max(0, m.start() - 800)
        window = _strip_tags(html_body[start : m.end() + 200])

        title_m = _WINDOW_TITLE_RE.search(window)
        title = title_m.group(1).strip() if title_m else "Unknown Title"
        company = _find_company(window)

        jobs.append(
            {
                "title": title,
                "company": company,
                "url": f"https://www.linkedin.com/jobs/view/{job_id}",
            }
        )

    return jobs


def filter_by_seniority(
    jobs: list[dict],
    keywords: Optional[list[str]] = None,
) -> list[dict]:
    """Keep only postings whose title contains at least one seniority keyword."""
    if keywords is None:
        keywords = DEFAULT_SENIORITY_KEYWORDS
    kw_lower = [k.lower() for k in keywords]
    return [j for j in jobs if any(kw in j["title"].lower() for kw in kw_lower)]
