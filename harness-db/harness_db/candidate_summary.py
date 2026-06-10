"""Deterministically assemble ``candidate-summary.json`` (spec 14 A4).

The compact profile every pipeline module reads used to be re-synthesised by a
sonnet model from the resume YAML *every day* — the single highest-leverage
hallucination point in the pipeline. This builds it deterministically instead:

* ``name`` / ``location`` / ``stack`` come from the resume YAML;
* ``target_titles`` / ``seniority_keywords`` / ``domains`` come from the DB
  target-roles (the same data ``target-roles show`` renders);
* ``headline`` / ``notable`` / ``years_experience`` / ``requirements`` come from
  the per-user config keys (editable in Settings).

The output schema stays byte-compatible with the file the job-seeker used to
write (``api_search.candidate``, ``harness_db.profile``, and the scorer all read
it); an extra ``inputs_hash`` makes ``--write`` idempotent — it only rewrites
when the inputs (resume bytes + rendered target roles + config values) change,
so a fresh ``generated`` date alone never churns the file.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import yaml

from harness_db import target_roles
from harness_db.config import get_job_data_root
from harness_db.config_store import get_config_optional

__all__ = ["CANDIDATE_CONFIG_KEYS", "build_summary", "write_summary"]

_SUMMARY_FILENAME = "candidate-summary.json"

# Per-user config keys this summary draws judgment fields from. Defaults are
# applied in :func:`build_summary` when a key is unset.
CANDIDATE_CONFIG_KEYS = (
    "CANDIDATE_HEADLINE",
    "CANDIDATE_NOTABLE",
    "CANDIDATE_YEARS_EXPERIENCE",
    "CANDIDATE_WORK_TYPE",
    "CANDIDATE_ELIGIBILITY",
    "CANDIDATE_EMPLOYMENT",
    "CANDIDATE_COMP_FLOOR_CAD",
)

_DEFAULT_WORK_TYPE = "fully remote"
_DEFAULT_ELIGIBILITY = "Canada-eligible"
_DEFAULT_EMPLOYMENT = "full-time,contract,freelance"


def _load_resume(uid: str | None) -> tuple[bytes, dict]:
    path = get_config_optional("RESUME_FILE", uid)
    if not path:
        raise RuntimeError("RESUME_FILE is not configured (set it in Settings or the env).")
    raw = Path(path).read_bytes()
    data = yaml.safe_load(raw) or {}
    return raw, (data.get("cv", {}) or {})


def _stack_from_cv(cv: dict) -> list[str]:
    """Comma-split every skills ``details`` line, stripped, order-preserving, deduped."""
    out: list[str] = []
    seen: set[str] = set()
    for entry in cv.get("sections", {}).get("skills", []) or []:
        for token in (entry.get("details", "") or "").split(","):
            value = token.strip()
            if value and value not in seen:
                seen.add(value)
                out.append(value)
    return out


def _requirements(uid: str | None) -> dict:
    employment_raw = get_config_optional("CANDIDATE_EMPLOYMENT", uid) or _DEFAULT_EMPLOYMENT
    requirements: dict = {
        "work_type": get_config_optional("CANDIDATE_WORK_TYPE", uid) or _DEFAULT_WORK_TYPE,
        "eligibility": get_config_optional("CANDIDATE_ELIGIBILITY", uid) or _DEFAULT_ELIGIBILITY,
        "employment": [e.strip() for e in employment_raw.split(",") if e.strip()],
    }
    comp_floor = get_config_optional("CANDIDATE_COMP_FLOOR_CAD", uid)
    if comp_floor:
        try:
            requirements["comp_floor_cad"] = int(comp_floor)
        except ValueError:
            pass
    return requirements


def _years_experience(uid: str | None) -> int | str:
    value = get_config_optional("CANDIDATE_YEARS_EXPERIENCE", uid)
    if not value:
        return ""
    try:
        return int(value)
    except ValueError:
        return ""


def _inputs_hash(resume_bytes: bytes, target_md: str, config_values: dict) -> str:
    """Stable hash of everything that should trigger a rewrite (not ``generated``)."""
    h = hashlib.sha256()
    h.update(resume_bytes)
    h.update(target_md.encode("utf-8"))
    h.update(json.dumps(config_values, sort_keys=True).encode("utf-8"))
    return h.hexdigest()


def build_summary(uid: str | None = None) -> dict:
    """Assemble the candidate summary dict (does not write anything)."""
    resume_bytes, cv = _load_resume(uid)
    target_md = target_roles.render_target_roles_md(uid)
    config_values = {k: get_config_optional(k, uid) for k in CANDIDATE_CONFIG_KEYS}

    return {
        "generated": date.today().isoformat(),
        "name": cv.get("name", "") or "",
        "headline": get_config_optional("CANDIDATE_HEADLINE", uid) or "",
        "location": cv.get("location", "") or "",
        "years_experience": _years_experience(uid),
        "notable": get_config_optional("CANDIDATE_NOTABLE", uid) or "",
        "stack": _stack_from_cv(cv),
        "domains": target_roles.enabled_values("domain", uid),
        "target_titles": target_roles.enabled_values("title", uid),
        "seniority_keywords": target_roles.enabled_values("keyword", uid),
        "requirements": _requirements(uid),
        "inputs_hash": _inputs_hash(resume_bytes, target_md, config_values),
    }


def write_summary(force: bool = False, uid: str | None = None) -> tuple[dict, bool]:
    """Build the summary and write it iff its ``inputs_hash`` changed (or ``force``).

    Returns ``(summary, wrote)``.
    """
    summary = build_summary(uid)
    path = get_job_data_root() / _SUMMARY_FILENAME

    existing_hash: str | None = None
    if path.exists():
        try:
            existing_hash = json.loads(path.read_text()).get("inputs_hash")
        except (json.JSONDecodeError, OSError):
            existing_hash = None

    wrote = False
    if force or existing_hash != summary["inputs_hash"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2))
        wrote = True
    return summary, wrote
