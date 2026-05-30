"""Reporting over harness DB postings.

Replaces the recurring ad-hoc one-liners (status counts, score buckets, top-N
listings) that parsed MCP tool-result text dumps. Everything here operates on
``list[Posting]`` loaded once via :func:`harness_db.queries.get_postings`, so the
DB is read through the shared model rather than re-parsed from scratch.
"""

from __future__ import annotations

from collections.abc import Iterable

from harness_db.models import Posting
from harness_db.queries import _UNKNOWN_STATE_PRIORITY, STATE_ORDER

__all__ = [
    "status_summary",
    "score_histogram",
    "top_postings",
    "render_report",
]

# Width of each score bucket in the histogram (0-9, 10-19, ...).
_BUCKET_SIZE = 10


def status_summary(postings: Iterable[Posting]) -> list[tuple[str, int]]:
    """Count postings by status, ordered by pipeline state then status name."""
    counts: dict[str, int] = {}
    for p in postings:
        status = p.status or "new"
        counts[status] = counts.get(status, 0) + 1
    return sorted(
        counts.items(),
        key=lambda kv: (STATE_ORDER.get(kv[0], _UNKNOWN_STATE_PRIORITY), kv[0]),
    )


def score_histogram(postings: Iterable[Posting]) -> list[tuple[str, int]]:
    """Bucket scored postings by ``final_score`` into 10-point bands, high first."""
    buckets: dict[int, int] = {}
    for p in postings:
        if p.final_score is None:
            continue
        floor = (p.final_score // _BUCKET_SIZE) * _BUCKET_SIZE
        buckets[floor] = buckets.get(floor, 0) + 1
    return [
        (f"{floor}-{floor + _BUCKET_SIZE - 1}", buckets[floor])
        for floor in sorted(buckets, reverse=True)
    ]


def top_postings(
    postings: Iterable[Posting],
    *,
    min_score: int = 75,
    limit: int = 15,
    scored_on: str | None = None,
) -> list[Posting]:
    """Highest-fit scored postings, best opportunity first.

    Keeps ``scored`` postings with ``final_score >= min_score`` (optionally only
    those scored on the ``scored_on`` date prefix, e.g. ``2026-05-29``), ordered by
    score descending then fewest applicants first (unknown applicant counts last).
    """
    matches = [
        p
        for p in postings
        if p.status == "scored"
        and p.final_score is not None
        and p.final_score >= min_score
        and (scored_on is None or (p.scored_date or "").startswith(scored_on))
    ]
    matches.sort(key=lambda p: (p.applicant_count is None, p.applicant_count or 0))
    matches.sort(key=lambda p: p.final_score or 0, reverse=True)
    return matches[:limit]


def _render_section(title: str, rows: list[str]) -> list[str]:
    out = [title, "-" * len(title)]
    out.extend(rows or ["(none)"])
    return out


def render_report(
    postings: list[Posting],
    *,
    min_score: int = 75,
    top: int = 15,
    scored_on: str | None = None,
) -> str:
    """Render the status summary, score histogram, and top-N table as text."""
    lines: list[str] = [f"Postings: {len(postings)}", ""]

    lines += _render_section(
        "By status",
        [f"  {status:<10} {count}" for status, count in status_summary(postings)],
    )
    lines.append("")

    lines += _render_section(
        "Score distribution (scored only)",
        [f"  {band:<8} {count}" for band, count in score_histogram(postings)],
    )
    lines.append("")

    scope = f" scored {scored_on}" if scored_on else ""
    leaders = top_postings(postings, min_score=min_score, limit=top, scored_on=scored_on)
    rows = [
        f"  {p.final_score:>3}  {(str(p.applicant_count) if p.applicant_count is not None else '?'):>4} appl  "
        f"{(p.company or '?')[:28]:<28}  {(p.title or '?')[:40]}"
        for p in leaders
    ]
    lines += _render_section(f"Top {top} (score >= {min_score}{scope})", rows)

    return "\n".join(lines)
