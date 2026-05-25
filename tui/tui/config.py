from __future__ import annotations

import json
import os
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).parent.parent


def get_db_path() -> Path:
    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        settings = _repo_root() / ".claude" / "settings.local.json"
        if settings.exists():
            data = json.loads(settings.read_text())
            job_data_root = data.get("env", {}).get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError(
            "JOB_DATA_ROOT not set. "
            "Add it to .claude/settings.local.json under env.JOB_DATA_ROOT."
        )
    return Path(job_data_root) / "jobs" / "postings.db"
