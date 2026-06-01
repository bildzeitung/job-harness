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
    "report_data",
    "render_report",
]

# Width of each score bucket in the histogram (0-9, 10-19, ...).
_BUCKET_SIZE = 10

# Per-posting fields exposed in the JSON report's "top" list — everything a caller
# needs to rank, present, and map back to a posting, minus job_description_text
# (large, and re-fetched on demand during preparation).
_TOP_FIELDS = (
    "url",
    "title",
    "company",
    "platform",
    "post_date",
    "applicant_count",
    "final_score",
    "base_score",
    "modifier",
    "scoring_notes",
    "dimension_scores",
    "scored_date",
)


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


def report_data(
    postings: list[Posting],
    *,
    min_score: int = 75,
    top: int = 15,
    scored_on: str | None = None,
) -> dict:
    """Structured report for JSON consumers (e.g. job-preparer's ranking step).

    Mirrors :func:`render_report` but returns data instead of text: status counts,
    score histogram, the ranked top-N (each a dict of :data:`_TOP_FIELDS`), and the
    count of in-scope scored postings that fell below ``min_score`` — so callers no
    longer hand-roll SQL and ranking to build their candidate list.
    """
    in_scope = [
        p
        for p in postings
        if p.status == "scored"
        and p.final_score is not None
        and (scored_on is None or (p.scored_date or "").startswith(scored_on))
    ]
    leaders = top_postings(postings, min_score=min_score, limit=top, scored_on=scored_on)
    return {
        "total": len(postings),
        "min_score": min_score,
        "scored_on": scored_on,
        "scored_total": len(in_scope),
        "scored_below_min": sum(1 for p in in_scope if p.final_score < min_score),
        "by_status": [{"status": s, "count": c} for s, c in status_summary(postings)],
        "score_distribution": [{"band": b, "count": c} for b, c in score_histogram(postings)],
        "top": [{field: getattr(p, field) for field in _TOP_FIELDS} for p in leaders],
    }


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
