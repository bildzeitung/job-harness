"""Consolidate per-platform job-seeker temp files into the harness DB.

Reads `$JOB_DATA_ROOT/jobs/{platform}-{date}.json` for each known platform,
deduplicates against the postings already in SQLite, writes the audit log
`$JOB_DATA_ROOT/jobs/search-{date}.json`, and inserts new rows
(company → posting → company_posting) in a single transaction.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from harness_db.models import Company, CompanyPosting, Posting, make_engine
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

PLATFORMS = ["linkedin", "indeed", "adzuna", "ziprecruiter", "greenhouse", "lever", "research"]


def _resolve_paths() -> tuple[Path, Path]:
    job_data_root = os.environ.get("JOB_DATA_ROOT", "")
    if not job_data_root:
        raise RuntimeError(
            "JOB_DATA_ROOT not set. Add it to .claude/settings.local.json under env.JOB_DATA_ROOT."
        )
    root = Path(job_data_root)
    db_path = Path(os.environ.get("SQLITE_DB_PATH") or root / "jobs" / "postings.db")
    return root, db_path


def _load_platform_file(jobs_dir: Path, platform: str, batch_date: str) -> list[dict[str, Any]]:
    """Return the postings list from {platform}-{date}.json, or [] if the file is absent.

    Platform-tags any posting that's missing the field so the audit log and DB rows
    are always attributable.
    """
    f = jobs_dir / f"{platform}-{batch_date}.json"
    if not f.exists():
        return []
    try:
        with open(f) as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[WARN] Could not read {f}: {exc}", file=sys.stderr)
        return []
    if isinstance(data, list):
        postings = data
    elif isinstance(data, dict):
        postings = data.get("postings", [])
    else:
        postings = []
    for p in postings:
        p.setdefault("platform", platform)
    return postings


def _dedup(
    raw: list[dict[str, Any]],
    existing_urls: set[str],
) -> tuple[list[dict[str, Any]], int, int]:
    """Drop URLs already in the DB and within-batch duplicates (keep first occurrence)."""
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    removed_existing = 0
    removed_within = 0
    for p in raw:
        url = p.get("url")
        if not url:
            continue
        if url in existing_urls:
            removed_existing += 1
        elif url in seen:
            removed_within += 1
        else:
            seen.add(url)
            deduped.append(p)
    return deduped, removed_existing, removed_within


def _write_audit_log(
    out_path: Path,
    batch_date: str,
    by_platform: dict[str, int],
    deduped: list[dict[str, Any]],
) -> None:
    payload = {
        "search_date": batch_date,
        "total_found": len(deduped),
        "by_platform": {p: by_platform.get(p, 0) for p in PLATFORMS},
        "postings": [
            {
                "title": p.get("title"),
                "company": p.get("company"),
                "url": p.get("url"),
                "platform": p.get("platform"),
                "post_date": p.get("post_date"),
                "applicant_count": p.get("applicant_count"),
                "employment_type": p.get("employment_type"),
                "location_note": p.get("location_note"),
                "description_summary": p.get("description_summary"),
                "job_description_text": p.get("job_description_text"),
            }
            for p in deduped
        ],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)


def _insert_rows(
    engine,
    deduped: list[dict[str, Any]],
    batch_date: str,
) -> int:
    """Insert company → posting → company_posting for each new posting.

    Uses INSERT … ON CONFLICT DO NOTHING so existing company rows (which
    sub-agents like adzuna may already have enriched with canada_confirmed)
    are preserved.
    """
    if not deduped:
        return 0

    with Session(engine) as session:
        for p in deduped:
            url = p["url"]
            company = (p.get("company") or "").strip()

            if company:
                session.execute(
                    sqlite_insert(Company)
                    .values(name=company, last_seen_date=batch_date)
                    .on_conflict_do_nothing(index_elements=[Company.name])
                )

            session.execute(
                sqlite_insert(Posting)
                .values(
                    url=url,
                    title=p.get("title"),
                    company=company or None,
                    platform=p.get("platform"),
                    post_date=p.get("post_date"),
                    applicant_count=p.get("applicant_count"),
                    employment_type=p.get("employment_type"),
                    location_note=p.get("location_note"),
                    description_summary=p.get("description_summary"),
                    job_description_text=p.get("job_description_text"),
                    first_seen=batch_date,
                    status="new",
                )
                .on_conflict_do_nothing(index_elements=[Posting.url])
            )

            if company:
                session.execute(
                    sqlite_insert(CompanyPosting)
                    .values(url=url, company_name=company)
                    .on_conflict_do_nothing(index_elements=[CompanyPosting.url])
                )

        session.commit()
    return len(deduped)


def consolidate(batch_date: str) -> int:
    """Merge temp files for `batch_date`, dedup, write audit log, insert into DB.

    Returns the number of new postings inserted.
    """
    root, db_path = _resolve_paths()
    jobs_dir = root / "jobs"
    if not jobs_dir.is_dir():
        raise RuntimeError(f"Jobs directory not found: {jobs_dir}")

    merged: list[dict[str, Any]] = []
    by_platform: dict[str, int] = {}
    for platform in PLATFORMS:
        items = _load_platform_file(jobs_dir, platform, batch_date)
        by_platform[platform] = len(items)
        merged.extend(items)

    engine = make_engine(db_path)
    with Session(engine) as session:
        existing_urls = {row[0] for row in session.execute(select(Posting.url)).all()}

    deduped, removed_existing, removed_within = _dedup(merged, existing_urls)

    audit_path = jobs_dir / f"search-{batch_date}.json"
    _write_audit_log(audit_path, batch_date, by_platform, deduped)

    inserted = _insert_rows(engine, deduped, batch_date)

    print("=== Consolidation Summary ===", flush=True)
    print(f"Batch date:        {batch_date}", flush=True)
    print(f"DB:                {db_path}", flush=True)
    print("By platform (raw, before dedup):", flush=True)
    for platform in PLATFORMS:
        print(f"  {platform:14s} {by_platform.get(platform, 0)}", flush=True)
    print(f"Total raw:         {len(merged)}", flush=True)
    print(f"Removed (in DB):   {removed_existing}", flush=True)
    print(f"Removed (in-batch):{removed_within}", flush=True)
    print(f"New inserted:      {inserted}", flush=True)
    print(f"Audit log:         {audit_path}", flush=True)
    return inserted
