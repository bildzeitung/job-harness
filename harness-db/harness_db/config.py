"""Locate the job-harness data root and SQLite database.

Promoted out of the TUI so every front-end and module resolves these the same way:
the JOB_DATA_ROOT env var first, then env.JOB_DATA_ROOT in .claude/settings.local.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = ["get_job_data_root", "get_db_path"]

_DB_RELATIVE_PATH = ("jobs", "postings.db")


def _repo_root() -> Path | None:
    """Walk up from cwd to the repo root (dir/file named .git), or None if absent."""
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def get_job_data_root() -> Path:
    """Resolve JOB_DATA_ROOT: env var first, then .claude/settings.local.json fallback."""
    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        repo_root = _repo_root()
        settings = repo_root / ".claude" / "settings.local.json" if repo_root else None
        if settings and settings.exists():
            try:
                data = json.loads(settings.read_text())
            except ValueError as e:
                raise RuntimeError(f"Malformed {settings}: {e}") from e
            job_data_root = data.get("env", {}).get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError(
            "JOB_DATA_ROOT not set. Add it to .claude/settings.local.json under env.JOB_DATA_ROOT."
        )
    return Path(job_data_root)


def get_db_path() -> Path:
    return get_job_data_root().joinpath(*_DB_RELATIVE_PATH)
