"""Source registry: one entry per web-API job source.

Each source contributes a `fetch` generator that yields *normalized* raw jobs —
plain dicts with the keys ``title``, ``company``, ``url``, ``post_date``,
``location`` and ``description``. The shared pipeline in :mod:`api_search.core`
then filters, dedups, and shapes those into final posting records, so adding a
new source means writing one generator and one registry entry — no changes to
the filtering/output code. Per-source data (company slugs, query tunables)
lives in the packaged ``sources_default.yaml``.
"""

from __future__ import annotations

import html
import os
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
import yaml

from api_search.candidate import queries_from_summary

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"
GREENHOUSE_BOARD = "https://boards-api.greenhouse.io/v1/boards/{slug}"
LEVER_POSTINGS = "https://api.lever.co/v0/postings/{slug}"
ASHBY_BOARD = "https://api.ashbyhq.com/posting-api/job-board/{slug}"
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
WORKABLE_WIDGET = "https://apply.workable.com/api/v1/widget/accounts/{slug}"
RECRUITEE_OFFERS = "https://{slug}.recruitee.com/api/offers/"
HIMALAYAS_URL = "https://himalayas.app/jobs/api"
WWR_RSS = "https://weworkremotely.com/categories/{category}.rss"

# Region / location-restriction tokens that admit a Canadian applicant. Used to
# keep the global remote-aggregator sources (Remotive, Himalayas, We Work
# Remotely) Canada-relevant — a restriction naming only non-Canada regions
# (e.g. "USA Only", "Europe Only") is dropped at the source.
_CANADA_OK_TOKENS = ("canada", "worldwide", "anywhere", "americas", "north america", "global")

# Cap on concurrent HTTP fetches within a single source (Adzuna queries, or
# Greenhouse/Lever boards). httpx.Client is thread-safe, so each work item
# (one query or one slug) runs on its own thread up to this many at a time.
MAX_FETCH_WORKERS = 8

# Adzuna is a single rate-limited search API (unlike the per-board ATS endpoints,
# which tolerate the full fan-out). Firing all target-title queries at once trips
# its free-tier limit — the 2026-06-07 run lost 4 of 8 queries to HTTP 429 — so
# Adzuna gets its own low concurrency plus a 429-aware retry (see _adzuna_get).
ADZUNA_MAX_WORKERS = 2
ADZUNA_MAX_RETRIES = 3
ADZUNA_BACKOFF_BASE = 2.0

_T = TypeVar("_T")

_CONFIG_PATH = Path(__file__).with_name("sources_default.yaml")

FetchFn = Callable[[httpx.Client, dict, dict], Iterator[dict[str, Any]]]


@dataclass(frozen=True)
class Source:
    """A web-API job source.

    `platform` is the value written to ``posting.platform`` and used as the
    ``{platform}-{date}.json`` filename prefix the consolidator reads.
    """

    name: str
    platform: str
    employment_type: str
    location_note: str
    fetch: FetchFn


@lru_cache(maxsize=1)
def load_config() -> dict[str, dict[str, Any]]:
    """Load the packaged per-source data file (slug lists, query tunables)."""
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f) or {}


def _strip_html(text: str) -> str:
    """Unescape HTML entities and strip tags, collapsing whitespace."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    return re.sub(r"\s+", " ", text).strip()


def _slug_to_name(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _epoch_ms_to_date(ms: Any) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def _epoch_s_to_date(s: Any) -> str | None:
    if not s:
        return None
    try:
        return datetime.fromtimestamp(int(s), tz=timezone.utc).date().isoformat()
    except (ValueError, OverflowError, OSError, TypeError):
        return None


def _rfc822_to_date(value: str) -> str | None:
    """Parse an RSS RFC-822 `pubDate` (e.g. 'Sun, 17 May 2026 20:30:53 +0000') to a date."""
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).date().isoformat()
    except (ValueError, TypeError):
        return None


def _rss_text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    return (el.text or "").strip() if el is not None else ""


def _canada_eligible(restriction: str) -> bool:
    """True if a remote board's region/restriction string admits a Canadian applicant.

    Empty/unknown restrictions are treated as eligible (don't over-filter); a
    restriction that names regions but none Canada-inclusive is rejected.
    """
    r = (restriction or "").lower().strip()
    if not r:
        return True
    return any(tok in r for tok in _CANADA_OK_TOKENS)


# ── parallel fan-out ────────────────────────────────────────────────────────


def _fetch_in_parallel(
    work_items: list[_T],
    worker: Callable[[_T], list[dict[str, Any]]],
    max_workers: int = MAX_FETCH_WORKERS,
) -> Iterator[dict[str, Any]]:
    """Run `worker` over `work_items` concurrently, yielding each item's records.

    Each `worker` handles its own errors and returns a (possibly empty) list, so
    one slow or failing query/board never blocks or aborts the others. Results
    are yielded in `work_items` order, keeping output stable and deterministic.

    `max_workers` caps concurrency; sources hitting a single rate-limited API
    (e.g. Adzuna) pass a smaller value than the default board fan-out.
    """
    if not work_items:
        return
    with ThreadPoolExecutor(max_workers=min(max_workers, len(work_items))) as pool:
        for records in pool.map(worker, work_items):
            yield from records


# ── fetch generators ──────────────────────────────────────────────────────────


def _adzuna_get(client: httpx.Client, params: dict[str, Any]) -> httpx.Response:
    """GET the Adzuna endpoint, retrying HTTP 429 with Retry-After/backoff.

    Adzuna's free tier rate-limits, so a 429 is transient — wait the server's
    `Retry-After` (or an exponential backoff) and try again rather than dropping
    the query. Other HTTP errors raise immediately via `raise_for_status`.
    """
    for attempt in range(ADZUNA_MAX_RETRIES + 1):
        resp = client.get(ADZUNA_URL, params=params)
        if resp.status_code == 429 and attempt < ADZUNA_MAX_RETRIES:
            retry_after = resp.headers.get("Retry-After")
            try:
                wait = float(retry_after) if retry_after else ADZUNA_BACKOFF_BASE ** (attempt + 1)
            except ValueError:
                wait = ADZUNA_BACKOFF_BASE ** (attempt + 1)
            print(
                f"[ADZUNA] HTTP 429 (attempt {attempt + 1}/{ADZUNA_MAX_RETRIES}), "
                f"retrying in {wait:.0f}s",
                flush=True,
            )
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    resp.raise_for_status()
    return resp


def fetch_adzuna(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Keyword search against the Adzuna Canada endpoint, one query per target title."""
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_API_KEY"]

    def _fetch_query(q: str) -> list[dict[str, Any]]:
        try:
            resp = _adzuna_get(
                client,
                {
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": cfg.get("results_per_page", 50),
                    "what": q,
                    "full_time": cfg.get("full_time", 1),
                },
            )
            data = resp.json()
        except Exception as e:
            print(f'[ADZUNA] Query "{q}" failed: {e}', flush=True)
            return []

        return [
            {
                "title": job.get("title", ""),
                "company": job.get("company", {}).get("display_name", ""),
                "url": job.get("redirect_url", ""),
                "post_date": (job.get("created", "") or "")[:10],
                "location": "",
                "description": job.get("description", "") or "",
            }
            for job in data.get("results", [])
        ]

    # Low concurrency so the per-query 429 retry isn't fighting a flood of our own
    # parallel requests — the rate-limited single endpoint, unlike the ATS boards.
    yield from _fetch_in_parallel(
        queries_from_summary(summary), _fetch_query, max_workers=ADZUNA_MAX_WORKERS
    )


def fetch_greenhouse(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull every job from each configured Greenhouse board (content included)."""

    def _fetch_board(slug: str) -> list[dict[str, Any]]:
        try:
            meta = client.get(GREENHOUSE_BOARD.format(slug=slug))
            meta.raise_for_status()
            company = meta.json().get("name") or _slug_to_name(slug)
        except Exception:
            company = _slug_to_name(slug)

        try:
            resp = client.get(
                GREENHOUSE_BOARD.format(slug=slug) + "/jobs", params={"content": "true"}
            )
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
        except Exception as e:
            print(f"[GREENHOUSE] Board '{slug}' failed: {e}", flush=True)
            return []

        records = []
        for job in jobs:
            location = (job.get("location") or {}).get("name", "") or ""
            records.append(
                {
                    "title": job.get("title", ""),
                    "company": company,
                    "url": job.get("absolute_url", ""),
                    "post_date": (job.get("updated_at") or "")[:10],
                    "location": location,
                    "description": _strip_html(job.get("content", "")),
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("slugs", []), _fetch_board)


def fetch_lever(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull every posting from each configured Lever board."""

    def _fetch_board(slug: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(LEVER_POSTINGS.format(slug=slug), params={"mode": "json"})
            resp.raise_for_status()
            postings = resp.json()
        except Exception as e:
            print(f"[LEVER] Board '{slug}' failed: {e}", flush=True)
            return []

        records = []
        for p in postings:
            cats = p.get("categories", {}) or {}
            description = p.get("descriptionPlain") or _strip_html(p.get("description", ""))
            records.append(
                {
                    "title": p.get("text", ""),
                    "company": _slug_to_name(slug),
                    "url": p.get("hostedUrl", ""),
                    "post_date": _epoch_ms_to_date(p.get("createdAt")),
                    "location": cats.get("location", "") or "",
                    "description": description,
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("slugs", []), _fetch_board)


def fetch_ashby(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull every posting from each configured Ashby public job board.

    Ashby's public ``posting-api`` endpoint returns the board's jobs but not the
    company name, so the slug (the ``jobs.ashbyhq.com/{slug}`` board id) is
    title-cased into a display name, mirroring the Lever fallback.
    """

    def _fetch_board(slug: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(ASHBY_BOARD.format(slug=slug), params={"includeCompensation": "true"})
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
        except Exception as e:
            print(f"[ASHBY] Board '{slug}' failed: {e}", flush=True)
            return []

        company = _slug_to_name(slug)
        records = []
        for job in jobs:
            if job.get("isListed") is False:
                continue
            description = job.get("descriptionPlain") or _strip_html(job.get("descriptionHtml", ""))
            records.append(
                {
                    "title": job.get("title", ""),
                    "company": company,
                    "url": job.get("jobUrl") or job.get("applyUrl", ""),
                    "post_date": (job.get("publishedAt") or "")[:10],
                    "location": job.get("location", "") or "",
                    "description": description,
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("slugs", []), _fetch_board)


def fetch_remotive(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Keyword search against the Remotive remote-jobs API, one query per target title.

    Remotive is a remote-only board, so the shared remote filter in
    :mod:`api_search.core` is effectively a no-op here; seniority and the
    prefilter still apply. Descriptions are HTML and get stripped.
    """
    limit = cfg.get("limit", 50)

    def _fetch_query(title: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(REMOTIVE_URL, params={"search": title, "limit": limit})
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
        except Exception as e:
            print(f'[REMOTIVE] Query "{title}" failed: {e}', flush=True)
            return []

        records = []
        for job in jobs:
            region = job.get("candidate_required_location", "") or ""
            if not _canada_eligible(region):
                continue
            records.append(
                {
                    "title": job.get("title", ""),
                    "company": (job.get("company_name") or "").strip(),
                    "url": job.get("url", ""),
                    "post_date": (job.get("publication_date") or "")[:10],
                    "location": f"Remote — {region}" if region else "Remote",
                    "description": _strip_html(job.get("description", "")),
                }
            )
        return records

    yield from _fetch_in_parallel(summary["target_titles"], _fetch_query)


HIMALAYAS_PAGE_SIZE = 20  # the public endpoint hard-caps each response at 20 jobs


def fetch_himalayas(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull Canada-eligible postings from the Himalayas remote-jobs API.

    Himalayas is a single recency-ordered feed (no keyword search) whose public
    endpoint returns at most 20 jobs per request, so this pages through it with
    `offset` (cfg `pages` × 20 postings) and drops any whose `locationRestrictions`
    exclude Canada; seniority is left to the shared title filter.
    """
    offsets = [i * HIMALAYAS_PAGE_SIZE for i in range(cfg.get("pages", 10))]

    def _fetch_page(offset: int) -> list[dict[str, Any]]:
        try:
            resp = client.get(
                HIMALAYAS_URL, params={"limit": HIMALAYAS_PAGE_SIZE, "offset": offset}
            )
            resp.raise_for_status()
            jobs = resp.json().get("jobs", [])
        except Exception as e:
            print(f"[HIMALAYAS] page offset={offset} failed: {e}", flush=True)
            return []

        records = []
        for job in jobs:
            restrictions = job.get("locationRestrictions") or []
            region = (
                ", ".join(restrictions) if isinstance(restrictions, list) else str(restrictions)
            )
            if not _canada_eligible(region):
                continue
            records.append(
                {
                    "title": job.get("title", ""),
                    "company": job.get("companyName", ""),
                    "url": job.get("applicationLink") or job.get("guid", ""),
                    "post_date": _epoch_s_to_date(job.get("pubDate")),
                    "location": f"Remote — {region}" if region else "Remote",
                    "description": _strip_html(job.get("description", "")),
                }
            )
        return records

    yield from _fetch_in_parallel(offsets, _fetch_page)


def fetch_wwr(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Parse Canada-eligible postings from each configured We Work Remotely RSS category.

    WWR item titles are ``"Company: Job Title"``; the `region` tag carries the
    geographic restriction used to drop non-Canada-eligible roles.
    """

    def _fetch_category(category: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(WWR_RSS.format(category=category))
            resp.raise_for_status()
            items = ET.fromstring(resp.text).findall(".//item")
        except Exception as e:
            print(f"[WWR] category '{category}' failed: {e}", flush=True)
            return []

        records = []
        for item in items:
            region = _rss_text(item, "region")
            if not _canada_eligible(region):
                continue
            company, sep, title = _rss_text(item, "title").partition(": ")
            if not sep:  # no "Company: Title" split — keep the whole string as the title
                company, title = "", company
            records.append(
                {
                    "title": title.strip(),
                    "company": company.strip(),
                    "url": _rss_text(item, "link"),
                    "post_date": _rfc822_to_date(_rss_text(item, "pubDate")),
                    "location": f"Remote — {region}" if region else "Remote",
                    "description": _strip_html(_rss_text(item, "description")),
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("categories", []), _fetch_category)


def fetch_workable(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull published jobs from each configured Workable public widget board.

    Workable boards include on-site roles, so each job's ``telecommuting`` flag is
    surfaced into the location text as "Remote" to drive the shared remote filter;
    non-remote jobs fall through it. ``details=true`` is required for descriptions.
    """

    def _fetch_board(slug: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(WORKABLE_WIDGET.format(slug=slug), params={"details": "true"})
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"[WORKABLE] Board '{slug}' failed: {e}", flush=True)
            return []

        company = data.get("name") or _slug_to_name(slug)
        records = []
        for job in data.get("jobs", []):
            if job.get("telecommuting"):
                location = "Remote"
            else:
                location = " ".join(p for p in (job.get("city"), job.get("country")) if p)
            records.append(
                {
                    "title": job.get("title", ""),
                    "company": company,
                    "url": job.get("url") or job.get("shortlink", ""),
                    "post_date": (job.get("published_on") or "")[:10],
                    "location": location,
                    "description": _strip_html(job.get("description", "")),
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("slugs", []), _fetch_board)


def fetch_recruitee(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Pull published offers from each configured Recruitee public board.

    Recruitee boards also include on-site roles, so the per-offer ``remote`` flag
    is folded into the location text to drive the shared remote filter.
    """

    def _fetch_board(slug: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(RECRUITEE_OFFERS.format(slug=slug))
            resp.raise_for_status()
            offers = resp.json().get("offers", [])
        except Exception as e:
            print(f"[RECRUITEE] Board '{slug}' failed: {e}", flush=True)
            return []

        records = []
        for o in offers:
            if o.get("status") and o.get("status") != "published":
                continue
            location = o.get("location") or ""
            if o.get("remote"):
                location = f"Remote {location}".strip()
            records.append(
                {
                    "title": o.get("title", ""),
                    "company": o.get("company_name") or _slug_to_name(slug),
                    "url": o.get("careers_url") or o.get("careers_apply_url", ""),
                    "post_date": (o.get("published_at") or "")[:10],
                    "location": location,
                    "description": _strip_html(o.get("description", "")),
                }
            )
        return records

    yield from _fetch_in_parallel(cfg.get("slugs", []), _fetch_board)


SOURCES: dict[str, Source] = {
    "adzuna": Source(
        name="adzuna",
        platform="adzuna",
        employment_type="full-time",
        location_note="Remote, Canada",
        fetch=fetch_adzuna,
    ),
    "greenhouse": Source(
        name="greenhouse",
        platform="greenhouse",
        employment_type="full-time",
        location_note="Remote, Canada OK",
        fetch=fetch_greenhouse,
    ),
    "lever": Source(
        name="lever",
        platform="lever",
        employment_type="full-time",
        location_note="Remote, Canada OK",
        fetch=fetch_lever,
    ),
    "ashby": Source(
        name="ashby",
        platform="ashby",
        employment_type="full-time",
        location_note="Remote, Canada OK",
        fetch=fetch_ashby,
    ),
    "workable": Source(
        name="workable",
        platform="workable",
        employment_type="full-time",
        location_note="Remote, Canada OK",
        fetch=fetch_workable,
    ),
    "recruitee": Source(
        name="recruitee",
        platform="recruitee",
        employment_type="full-time",
        location_note="Remote, Canada OK",
        fetch=fetch_recruitee,
    ),
    "remotive": Source(
        name="remotive",
        platform="remotive",
        employment_type="full-time",
        location_note="Remote",
        fetch=fetch_remotive,
    ),
    "himalayas": Source(
        name="himalayas",
        platform="himalayas",
        employment_type="full-time",
        location_note="Remote, Canada-eligible",
        fetch=fetch_himalayas,
    ),
    "wwr": Source(
        name="wwr",
        platform="wwr",
        employment_type="full-time",
        location_note="Remote, Canada-eligible",
        fetch=fetch_wwr,
    ),
}


def usage() -> str:
    return f"Usage: python -m api_search <source>\n  sources: {', '.join(SOURCES)}"


__all__ = ["SOURCES", "Source", "load_config", "usage"]
