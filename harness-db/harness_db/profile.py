"""Load the shared candidate profile written by the job-seeker.

`candidate-summary.json` is the compact profile every pipeline module reads
instead of re-parsing the full resume + config. Promoted here so api-search,
the scorer, and any future consumer share one loader and one path-resolution
rule (see :func:`harness_db.config.get_job_data_root`).
"""

from __future__ import annotations

import json

from harness_db.config import get_job_data_root

__all__ = ["load_candidate_summary"]

_SUMMARY_FILENAME = "candidate-summary.json"


def load_candidate_summary() -> dict:
    """Read `$JOB_DATA_ROOT/candidate-summary.json` (written by the job-seeker)."""
    path = get_job_data_root() / _SUMMARY_FILENAME
    if not path.exists():
        raise FileNotFoundError(f"{_SUMMARY_FILENAME} not found at {path}")
    with open(path) as f:
        return json.load(f)
