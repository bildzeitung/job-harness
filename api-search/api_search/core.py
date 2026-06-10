"""Run a source end-to-end: fetch → filter → dedup → shape → write the file."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from harness_db.disqualifiers import load_prefilter, prefilter_disqualifies, prefilter_match

from api_search.candidate import load_candidate_summary, seniority_keywords_from_summary
from api_search.filters import is_remote, is_senior
from api_search.sources import SOURCES, load_config

DESCRIPTION_SUMMARY_LEN = 300
JOB_DESCRIPTION_LEN = 8000


def dedup_by_url(postings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop postings with no URL or a URL already seen, keeping first occurrence.

    Shared by the API pipeline and the MCP searchers' merge path so both dedup
    identically. Order is preserved, so when ``existing + new`` is passed the
    existing record wins on a URL collision.
    """
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in postings:
        url = p.get("url") or ""
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(p)
    return out


def run(source_name: str, timeout: int = 20) -> list[dict[str, Any]]:
    """Fetch postings for `source_name`, apply the shared filters, dedup by URL.

    Returns final posting records in the consolidator's schema.
    """
    if source_name not in SOURCES:
        raise ValueError(f"Unknown source '{source_name}'. Known: {', '.join(SOURCES)}")

    src = SOURCES[source_name]
    summary = load_candidate_summary()
    seniority = seniority_keywords_from_summary(summary)
    prefilter = load_prefilter()
    cfg = load_config().get(source_name, {})

    seen: set[str] = set()
    results: list[dict[str, Any]] = []

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for raw in src.fetch(client, summary, cfg):
            url = raw.get("url") or ""
            if not url or url in seen:
                continue

            title = raw.get("title", "") or ""
            location = raw.get("location", "") or ""
            description = raw.get("description", "") or ""
            combined = f"{title} {location} {description}"

            if not is_remote(combined):
                continue
            if not is_senior(title, seniority):
                continue
            if prefilter_disqualifies(title, combined, prefilter):
                continue

            seen.add(url)
            results.append(
                {
                    "title": title,
                    "company": raw.get("company", ""),
                    "url": url,
                    "platform": src.platform,
                    "post_date": raw.get("post_date"),
                    "applicant_count": None,
                    "employment_type": src.employment_type,
                    "location_note": src.location_note,
                    "description_summary": description[:DESCRIPTION_SUMMARY_LEN],
                    "job_description_text": description[:JOB_DESCRIPTION_LEN] or None,
                }
            )

    return results


def inspect_batch(path: str | Path) -> dict[str, Any]:
    """Summarize a jobs ``{platform}-{date}.json`` file: shape, count, field coverage.

    Replaces the ad-hoc ``rtk read file | python3 -c "json.load; print keys"``
    one-liners agents hand-rolled to sanity-check an output file. Accepts either
    the consolidator object (``{search_date, platform, total_found, postings}``)
    or a bare array of postings.

    Returns ``{"shape", "meta", "count", "fields"}`` where ``fields`` maps each
    posting key to the number of postings that carry a non-empty value for it —
    surfacing partially-populated fields (e.g. a missing ``job_description_text``).
    """
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        shape = "object"
        meta = {k: data[k] for k in ("search_date", "platform", "total_found") if k in data}
        postings = data.get("postings", [])
    else:
        shape = "array"
        meta = {}
        postings = data
    if not isinstance(postings, list):
        postings = []

    fields: dict[str, int] = {}
    for p in postings:
        if not isinstance(p, dict):
            continue
        for key, value in p.items():
            fields.setdefault(key, 0)
            if value not in (None, "", [], {}):
                fields[key] += 1

    return {"shape": shape, "meta": meta, "count": len(postings), "fields": fields}


def _batch_path(platform: str, batch_date: str) -> Path:
    """Resolve `$JOB_DATA_ROOT/jobs/{platform}-{date}.json`, creating `jobs/`."""
    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError("JOB_DATA_ROOT is not set")
    out_path = Path(job_data_root) / "jobs" / f"{platform}-{batch_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return out_path


def _write_batch(out_path: Path, platform: str, batch_date: str, postings: list[dict[str, Any]]):
    out_path.write_text(
        json.dumps(
            {
                "search_date": batch_date,
                "platform": platform,
                "total_found": len(postings),
                "postings": postings,
            },
            indent=2,
        )
    )


def write_output(
    source_name: str,
    results: list[dict[str, Any]],
    batch_date: str | None = None,
) -> Path:
    """Overwrite `$JOB_DATA_ROOT/jobs/{platform}-{date}.json` in the consolidator schema.

    Used by the API pipeline, whose `run()` already produces the complete deduped
    set each invocation, so a full overwrite is the correct idempotent behavior.
    MCP searchers that accumulate across runs use :func:`append_postings` instead.
    """
    batch_date = batch_date or date.today().isoformat()
    platform = SOURCES[source_name].platform
    out_path = _batch_path(platform, batch_date)
    _write_batch(out_path, platform, batch_date, results)
    return out_path


def append_postings(
    platform: str,
    new_postings: list[dict[str, Any]],
    batch_date: str | None = None,
) -> dict[str, Any]:
    """Merge `new_postings` into `$JOB_DATA_ROOT/jobs/{platform}-{date}.json`.

    The shared writer for the MCP searchers (linkedin, indeed, ziprecruiter,
    research), replacing the ad-hoc load-existing/dedup/merge Python they used to
    regenerate each run. Existing records are kept and deduped against the new
    batch by URL (existing wins). A missing or unreadable file is treated as
    empty, so the first run behaves like a plain write.

    Each **incoming** posting is run through the hard prefilter
    (``prefilter_match``) before the merge, so an MCP searcher can write a
    completely unfiltered batch and the canonical file still contains zero
    prefilter-disqualified postings. Postings already in the file are not
    re-filtered — they passed when first appended. The prefilter is applied to
    ``title`` + ``location_note`` + ``description_summary`` + ``job_description_text``
    (the same fields ``run()`` combines).

    Dropped postings are not discarded silently: each is appended (with a
    ``matched_rule`` field naming the firing rule) to the audit sidecar
    ``{platform}-{date}.disqualified.json`` next to the canonical file, so an
    over-firing keyword can be traced and the posting recovered. The sidecar's
    name never collides with a consolidator platform file, so it is never
    ingested.

    Returns counts: ``{"path", "added", "total", "skipped", "disqualified"}``
    where ``added`` is the number of new URLs written, ``skipped`` the
    duplicate/blank-URL drops, and ``disqualified`` the prefilter drops.
    """
    batch_date = batch_date or date.today().isoformat()
    out_path = _batch_path(platform, batch_date)

    existing: list[dict[str, Any]] = []
    if out_path.exists():
        try:
            loaded = json.loads(out_path.read_text())
            postings = loaded.get("postings") if isinstance(loaded, dict) else None
            existing = postings if isinstance(postings, list) else []
        except (json.JSONDecodeError, OSError):
            existing = []

    prefilter = load_prefilter()
    kept_new: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for p in new_postings:
        title = p.get("title", "") or ""
        combined = " ".join(
            str(p.get(k, "") or "")
            for k in ("title", "location_note", "description_summary", "job_description_text")
        )
        rule = prefilter_match(title, combined, prefilter)
        if rule is not None:
            dropped.append({**p, "matched_rule": rule})
            continue
        kept_new.append(p)

    if dropped:
        _append_sidecar(out_path, platform, batch_date, dropped)

    existing_urls = {p.get("url") for p in existing if p.get("url")}
    merged = dedup_by_url(existing + kept_new)
    added = sum(1 for p in merged if p.get("url") not in existing_urls)
    _write_batch(out_path, platform, batch_date, merged)
    return {
        "path": str(out_path),
        "added": added,
        "total": len(merged),
        "skipped": len(kept_new) - added,
        "disqualified": len(dropped),
    }


def _append_sidecar(
    out_path: Path, platform: str, batch_date: str, dropped: list[dict[str, Any]]
) -> Path:
    """Merge prefilter-dropped postings into ``{platform}-{date}.disqualified.json``.

    Same merge semantics as the canonical file: existing records win on a URL
    collision, an unreadable file is treated as empty.
    """
    sidecar = out_path.with_name(f"{platform}-{batch_date}.disqualified.json")
    existing: list[dict[str, Any]] = []
    if sidecar.exists():
        try:
            loaded = json.loads(sidecar.read_text())
            postings = loaded.get("postings") if isinstance(loaded, dict) else None
            existing = postings if isinstance(postings, list) else []
        except (json.JSONDecodeError, OSError):
            existing = []
    merged = dedup_by_url(existing + dropped)
    sidecar.write_text(
        json.dumps(
            {
                "search_date": batch_date,
                "platform": platform,
                "total_dropped": len(merged),
                "postings": merged,
            },
            indent=2,
        )
    )
    return sidecar
