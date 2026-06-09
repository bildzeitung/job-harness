"""Locate the job-harness data root, SQLite database, and active user.

Promoted out of the TUI so every front-end and module resolves these the same way.
Resolution for any of these reads the process env var first, then
``env.<KEY>`` in ``.claude/settings.local.json`` as a fallback.

The SQLite DB is located by the ``HARNESS_DB`` env var (a path straight to the
file). This decouples the DB from ``JOB_DATA_ROOT`` so the latter can itself be a
DB-stored, per-user config item. For backward compatibility, if ``HARNESS_DB`` is
unset the DB falls back to ``$JOB_DATA_ROOT/jobs/postings.db`` (its historical
location).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

__all__ = [
    "get_job_data_root",
    "get_db_path",
    "get_active_uid",
    "set_active_uid",
    "DEFAULT_UID",
    "ACTIVE_USER_FILENAME",
]

_DB_RELATIVE_PATH = ("jobs", "postings.db")

DEFAULT_UID = "default"
ACTIVE_USER_FILENAME = ".active-user"


def _repo_root() -> Path | None:
    """Walk up from cwd to the repo root (dir/file named .git), or None if absent."""
    here = Path.cwd()
    for parent in [here, *here.parents]:
        if (parent / ".git").exists():
            return parent
    return None


def _settings_env(key: str) -> str | None:
    """Read ``env.<key>`` from .claude/settings.local.json, or None if absent."""
    repo_root = _repo_root()
    settings = repo_root / ".claude" / "settings.local.json" if repo_root else None
    if settings and settings.exists():
        try:
            data = json.loads(settings.read_text())
        except ValueError as e:
            raise RuntimeError(f"Malformed {settings}: {e}") from e
        return data.get("env", {}).get(key)
    return None


def _env_or_settings(key: str) -> str | None:
    """Process env var first, then the settings.local.json fallback."""
    return os.environ.get(key) or _settings_env(key)


def get_job_data_root() -> Path:
    """Resolve JOB_DATA_ROOT: env var first, then .claude/settings.local.json fallback."""
    job_data_root = _env_or_settings("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError(
            "JOB_DATA_ROOT not set. Add it to .claude/settings.local.json under env.JOB_DATA_ROOT."
        )
    return Path(job_data_root)


def get_db_path() -> Path:
    """Resolve the SQLite DB path: ``HARNESS_DB`` first, else ``$JOB_DATA_ROOT/jobs/postings.db``."""
    explicit = _env_or_settings("HARNESS_DB")
    if explicit:
        return Path(explicit)
    return get_job_data_root().joinpath(*_DB_RELATIVE_PATH)


def _active_user_pointer() -> Path:
    """The ``.active-user`` dotfile, kept beside the DB file (user-independent)."""
    return get_db_path().parent / ACTIVE_USER_FILENAME


def get_active_uid(cli: str | None = None) -> str:
    """Resolve the active user: explicit CLI value → .active-user dotfile → 'default'."""
    if cli:
        return cli
    pointer = _active_user_pointer()
    if pointer.exists():
        value = pointer.read_text().strip()
        if value:
            return value
    return DEFAULT_UID


def set_active_uid(uid: str) -> None:
    """Persist the active user to the ``.active-user`` dotfile beside the DB."""
    pointer = _active_user_pointer()
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(f"{uid}\n")
