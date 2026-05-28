"""Run a source end-to-end: fetch → filter → dedup → shape → write the file."""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from api_search.candidate import load_candidate_summary, seniority_keywords_from_summary
from api_search.filters import is_canada_eligible, is_junior, is_remote, is_senior
from api_search.sources import SOURCES, load_config

DESCRIPTION_SUMMARY_LEN = 300
JOB_DESCRIPTION_LEN = 8000


def run(source_name: str, timeout: int = 20) -> list[dict[str, Any]]:
    """Fetch postings for `source_name`, apply the shared filters, dedup by URL.

    Returns final posting records in the consolidator's schema.
    """
    if source_name not in SOURCES:
        raise ValueError(f"Unknown source '{source_name}'. Known: {', '.join(SOURCES)}")

    src = SOURCES[source_name]
    summary = load_candidate_summary()
    seniority = seniority_keywords_from_summary(summary)
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
            if is_junior(title):
                continue
            if not is_canada_eligible(combined):
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


def write_output(
    source_name: str,
    results: list[dict[str, Any]],
    batch_date: str | None = None,
) -> Path:
    """Write `$JOB_DATA_ROOT/jobs/{platform}-{date}.json` in the consolidator schema."""
    batch_date = batch_date or date.today().isoformat()
    platform = SOURCES[source_name].platform

    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError("JOB_DATA_ROOT is not set")

    out_path = Path(job_data_root) / "jobs" / f"{platform}-{batch_date}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "search_date": batch_date,
        "platform": platform,
        "total_found": len(results),
        "postings": results,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    return out_path
