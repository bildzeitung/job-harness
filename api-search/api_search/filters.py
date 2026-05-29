"""Shared posting filters — applied uniformly to every source's results.

Positive match filters (remote, seniority) live here. Hard exclusions are NOT
hard-coded: they come from the user-editable ``disqualifiers.yaml`` prefilter via
:func:`harness_db.disqualifiers.prefilter_disqualifies`, the single source of
truth shared with ``job-preparer`` and the scorer.
"""

from __future__ import annotations


def is_remote(text: str) -> bool:
    return "remote" in text.lower()


def is_senior(title: str, seniority_keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in seniority_keywords)
