"""Probe configured ATS board slugs and report dead or empty boards.

Board slugs in ``sources_default.yaml`` go stale fast — companies migrate ATS
(commonly to Ashby) and a dead board only surfaces as a quiet 404 with zero
results during a search run. ``python -m api_search probe-slugs`` hits each
slug's cheap JSON endpoint and reports its health so a human can relocate the
company to its new board (prefer relocating over deleting). Report-only: this
module never modifies the config.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import httpx

from api_search.sources import (
    ASHBY_BOARD,
    GREENHOUSE_BOARD,
    LEVER_POSTINGS,
    RECRUITEE_OFFERS,
    WORKABLE_WIDGET,
    load_config,
)

PROBE_TIMEOUT = 10

# Status buckets, in report order.
OK = "OK"
EMPTY = "EMPTY"
GONE = "GONE"
ERROR = "ERROR"


@dataclass(frozen=True)
class SlugProbe:
    """A slug-based source's cheap health endpoint and job-count extractor."""

    url_template: str
    params: dict[str, Any] | None
    count: Callable[[Any], int]


def _len_of(key: str) -> Callable[[Any], int]:
    return lambda data: len(data.get(key, [])) if isinstance(data, dict) else 0


PROBES: dict[str, SlugProbe] = {
    "greenhouse": SlugProbe(GREENHOUSE_BOARD + "/jobs", {"content": "false"}, _len_of("jobs")),
    "lever": SlugProbe(
        LEVER_POSTINGS, {"mode": "json"}, lambda d: len(d) if isinstance(d, list) else 0
    ),
    "ashby": SlugProbe(ASHBY_BOARD, None, _len_of("jobs")),
    "workable": SlugProbe(WORKABLE_WIDGET, None, _len_of("jobs")),
    "recruitee": SlugProbe(RECRUITEE_OFFERS, None, _len_of("offers")),
}


@dataclass(frozen=True)
class ProbeResult:
    source: str
    slug: str
    status: str  # OK | EMPTY | GONE | ERROR
    detail: str  # "12 jobs" | "HTTP 500" | exception text


def _probe_one(client: httpx.Client, source: str, probe: SlugProbe, slug: str) -> ProbeResult:
    url = probe.url_template.format(slug=slug)
    try:
        resp = client.get(url, params=probe.params)
    except Exception as exc:
        return ProbeResult(source, slug, ERROR, str(exc))
    if resp.status_code == 404:
        return ProbeResult(source, slug, GONE, "HTTP 404")
    if resp.status_code != 200:
        return ProbeResult(source, slug, ERROR, f"HTTP {resp.status_code}")
    try:
        n = probe.count(resp.json())
    except Exception as exc:
        return ProbeResult(source, slug, ERROR, f"bad JSON: {exc}")
    if n == 0:
        return ProbeResult(source, slug, EMPTY, "0 jobs")
    return ProbeResult(source, slug, OK, f"{n} jobs")


def probe_slugs(
    source_names: list[str] | None = None,
    timeout: int = PROBE_TIMEOUT,
    client: httpx.Client | None = None,
) -> list[ProbeResult]:
    """Probe every configured slug of the given sources (default: all slug-based).

    `client` is injectable for tests; when omitted a short-timeout client is used.
    """
    names = source_names or list(PROBES)
    unknown = [n for n in names if n not in PROBES]
    if unknown:
        raise ValueError(
            f"Not slug-based source(s): {', '.join(unknown)}. Known: {', '.join(PROBES)}"
        )

    cfg = load_config()
    results: list[ProbeResult] = []

    def _run(c: httpx.Client) -> None:
        for name in names:
            probe = PROBES[name]
            for slug in cfg.get(name, {}).get("slugs", []):
                results.append(_probe_one(c, name, probe, slug))

    if client is not None:
        _run(client)
    else:
        with httpx.Client(timeout=timeout, follow_redirects=True) as c:
            _run(c)
    return results
