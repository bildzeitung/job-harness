"""Upsert hiring-company records from a searcher's jobs batch.

Replaces the per-company ``INSERT … ON CONFLICT`` SQL each searcher hand-wrote
(dozens of tool calls per run) with one deterministic, unit-tested upsert. The
per-platform **flag policy** below is the single source of truth for the
ratchet/notes/last-seen semantics the agent SQL used to encode in prose.

A flag "ratchet" is monotonic 0→1: once a platform confirms remote/Canada the
flag stays 1 and is never lowered, matching the old
``MAX(COALESCE(existing, 0), 1)`` SQL. ``last_seen_date`` advances to the most
recent date seen. ``notes`` is filled only when empty (``fill``) except for the
research agent, whose composed per-company judgment overwrites (``overwrite``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from harness_db.models import Company

__all__ = ["PLATFORM_POLICY", "CompanyPolicy", "record_seen"]


@dataclass(frozen=True)
class CompanyPolicy:
    """How a platform's postings update the ``companies`` row.

    ``remote_confirmed`` / ``canada_confirmed`` ratchet the matching flag to 1
    (never down). ``notes_mode`` is ``none`` (leave notes alone), ``fill`` (set a
    default "Hiring on {board}" note only when notes are empty) or ``overwrite``
    (use the posting's ``company_notes`` when non-empty — research only).
    ``researched_date`` also stamps ``researched_date`` (research only).
    """

    remote_confirmed: bool
    canada_confirmed: bool
    notes_mode: str  # "none" | "fill" | "overwrite"
    researched_date: bool = False


# Single source of truth for the per-platform company-flag policy (spec 14 A2).
# Must cover every platform in consolidate_module.consolidator.PLATFORMS — the
# test_companies sync-guard enforces this (same idea as the BUILTIN_SOURCES memory).
PLATFORM_POLICY: dict[str, CompanyPolicy] = {
    # MCP boards that keep ambiguous Canada cases for the scorer — flags untouched.
    "linkedin": CompanyPolicy(False, False, "none"),
    "ziprecruiter": CompanyPolicy(False, False, "none"),
    # Country-scoped searches establish Canada eligibility at the job level.
    "indeed": CompanyPolicy(False, True, "none"),
    "adzuna": CompanyPolicy(False, True, "none"),
    # Public ATS APIs: the posting URL is the company's own careers page (remote +
    # Canada-eligible postings only reach here), so ratchet both.
    "greenhouse": CompanyPolicy(True, True, "fill"),
    "lever": CompanyPolicy(True, True, "fill"),
    "ashby": CompanyPolicy(True, True, "fill"),
    "workable": CompanyPolicy(True, True, "fill"),
    "recruitee": CompanyPolicy(True, True, "fill"),
    # Remote-jobs boards confirm remote but not a Canada office.
    "remotive": CompanyPolicy(True, False, "fill"),
    "himalayas": CompanyPolicy(True, False, "fill"),
    "wwr": CompanyPolicy(True, False, "fill"),
    # Research agent: manually verified both, composes its own per-company notes.
    "research": CompanyPolicy(True, True, "overwrite", researched_date=True),
}

# Display names for the "Hiring on {board}" default note (notes_mode == "fill").
_PLATFORM_DISPLAY: dict[str, str] = {
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
    "workable": "Workable",
    "recruitee": "Recruitee",
    "remotive": "Remotive",
    "himalayas": "Himalayas",
    "wwr": "We Work Remotely",
}


def _resolve_note(policy: CompanyPolicy, platform: str, posting: dict[str, Any]) -> str:
    if policy.notes_mode == "overwrite":
        return (posting.get("company_notes") or "").strip()
    if policy.notes_mode == "fill":
        display = _PLATFORM_DISPLAY.get(platform, platform.title())
        return f"Hiring on {display} (see posting URLs)"
    return ""


def _apply(row: Company, policy: CompanyPolicy, platform: str, posting: dict, batch_date: str):
    if policy.remote_confirmed:
        row.remote_confirmed = True  # ratchet to 1 (monotonic)
    if policy.canada_confirmed:
        row.canada_confirmed = True
    note = _resolve_note(policy, platform, posting)
    if note:
        if policy.notes_mode == "overwrite":
            row.notes = note
        elif not (row.notes or "").strip():
            row.notes = note
    if not row.last_seen_date or batch_date > row.last_seen_date:
        row.last_seen_date = batch_date
    if policy.researched_date:
        row.researched_date = batch_date


def record_seen(
    engine: Engine,
    postings: Iterable[dict[str, Any]],
    batch_date: str,
    default_platform: str | None = None,
) -> dict[str, int]:
    """Upsert one ``companies`` row per unique company in ``postings``.

    Each posting's platform (``posting['platform']`` → ``default_platform``)
    selects the :data:`PLATFORM_POLICY` entry applied. An unknown platform raises
    ``ValueError`` so a typo fails loudly instead of silently skipping companies.

    Returns ``{"companies": <unique names>, "inserted": <new rows this call>}``.
    """
    seen: set[str] = set()
    inserted = 0
    with Session(engine) as session:
        for p in postings:
            name = (p.get("company") or "").strip()
            if not name:
                continue
            platform = (p.get("platform") or default_platform or "").strip().lower()
            policy = PLATFORM_POLICY.get(platform)
            if policy is None:
                raise ValueError(
                    f"Unknown platform {platform!r} for company {name!r}. "
                    f"Known: {', '.join(sorted(PLATFORM_POLICY))}."
                )
            row = session.get(Company, name)
            if row is None:
                row = Company(name=name)
                session.add(row)
                if name not in seen:
                    inserted += 1
            _apply(row, policy, platform, p, batch_date)
            seen.add(name)
        session.commit()
    return {"companies": len(seen), "inserted": inserted}
