"""Load the candidate profile and derive search inputs from it."""

from __future__ import annotations

import json
import os
from pathlib import Path


def load_candidate_summary() -> dict:
    """Read `$JOB_DATA_ROOT/candidate-summary.json` (written by the job-seeker)."""
    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError("JOB_DATA_ROOT is not set")
    path = Path(job_data_root) / "candidate-summary.json"
    if not path.exists():
        raise FileNotFoundError(f"candidate-summary.json not found at {path}")
    with open(path) as f:
        return json.load(f)


def queries_from_summary(summary: dict) -> list[str]:
    """One `"{title} remote"` query per target title (used by keyword-search sources)."""
    return [f"{title} remote" for title in summary["target_titles"]]


def seniority_keywords_from_summary(summary: dict) -> list[str]:
    """Lower-cased seniority keywords used to filter job titles."""
    return [kw.lower() for kw in summary["seniority_keywords"]]
