"""Derive search inputs from the candidate profile.

The profile loader itself lives in :mod:`harness_db.profile` so every pipeline
module shares one implementation; it is re-exported here so existing
``api_search.candidate`` imports keep working unchanged.
"""

from __future__ import annotations

from harness_db.profile import load_candidate_summary

__all__ = [
    "load_candidate_summary",
    "queries_from_summary",
    "seniority_keywords_from_summary",
]


def queries_from_summary(summary: dict) -> list[str]:
    """One `"{title} remote"` query per target title (used by keyword-search sources)."""
    return [f"{title} remote" for title in summary["target_titles"]]


def seniority_keywords_from_summary(summary: dict) -> list[str]:
    """Lower-cased seniority keywords used to filter job titles."""
    return [kw.lower() for kw in summary["seniority_keywords"]]
