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
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

import httpx
import yaml

from api_search.candidate import queries_from_summary

ADZUNA_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"
GREENHOUSE_BOARD = "https://boards-api.greenhouse.io/v1/boards/{slug}"
LEVER_POSTINGS = "https://api.lever.co/v0/postings/{slug}"

# Cap on concurrent HTTP fetches within a single source (Adzuna queries, or
# Greenhouse/Lever boards). httpx.Client is thread-safe, so each work item
# (one query or one slug) runs on its own thread up to this many at a time.
MAX_FETCH_WORKERS = 8

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


# ── parallel fan-out ────────────────────────────────────────────────────────


def _fetch_in_parallel(
    work_items: list[_T],
    worker: Callable[[_T], list[dict[str, Any]]],
) -> Iterator[dict[str, Any]]:
    """Run `worker` over `work_items` concurrently, yielding each item's records.

    Each `worker` handles its own errors and returns a (possibly empty) list, so
    one slow or failing query/board never blocks or aborts the others. Results
    are yielded in `work_items` order, keeping output stable and deterministic.
    """
    if not work_items:
        return
    with ThreadPoolExecutor(max_workers=min(MAX_FETCH_WORKERS, len(work_items))) as pool:
        for records in pool.map(worker, work_items):
            yield from records


# ── fetch generators ──────────────────────────────────────────────────────────


def fetch_adzuna(client: httpx.Client, summary: dict, cfg: dict) -> Iterator[dict[str, Any]]:
    """Keyword search against the Adzuna Canada endpoint, one query per target title."""
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_API_KEY"]

    def _fetch_query(q: str) -> list[dict[str, Any]]:
        try:
            resp = client.get(
                ADZUNA_URL,
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "results_per_page": cfg.get("results_per_page", 50),
                    "what": q,
                    "full_time": cfg.get("full_time", 1),
                },
            )
            resp.raise_for_status()
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

    yield from _fetch_in_parallel(queries_from_summary(summary), _fetch_query)


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
}


def usage() -> str:
    return f"Usage: python -m api_search <source>\n  sources: {', '.join(SOURCES)}"


__all__ = ["SOURCES", "Source", "load_config", "usage"]
