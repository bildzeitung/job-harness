"""Serializable view models bridging SQLAlchemy ORM rows to Reflex state vars.

Reflex state vars must be JSON-serializable, so ORM objects cannot be stored
directly. These dataclasses carry exactly what the UI renders, with detail text
precomputed to mirror the TUI's detail panels.
"""

from __future__ import annotations

import dataclasses

from harness_db.models import Company, Posting

from web.theme import GLYPH_FALSE, GLYPH_TRUE, GLYPH_UNKNOWN, state_color


def _bool_glyph(value: bool | None) -> str:
    if value is True:
        return GLYPH_TRUE
    if value is False:
        return GLYPH_FALSE
    return GLYPH_UNKNOWN


@dataclasses.dataclass
class PostingVM:
    url: str
    title: str | None
    company: str | None
    display_name: str
    display_date: str
    status: str
    status_color: str
    detail_text: str

    @classmethod
    def from_orm(cls, p: Posting) -> "PostingVM":
        return cls(
            url=p.url,
            title=p.title,
            company=p.company,
            display_name=p.display_name,
            display_date=p.display_date,
            status=p.status or "new",
            status_color=state_color(p.status),
            detail_text=_format_posting_detail(p),
        )


@dataclasses.dataclass
class CompanyVM:
    name: str
    remote: str
    canada: str
    last_seen: str
    notes: str
    detail_text: str

    @classmethod
    def from_orm(cls, c: Company) -> "CompanyVM":
        return cls(
            name=c.name or GLYPH_UNKNOWN,
            remote=_bool_glyph(c.remote_confirmed),
            canada=_bool_glyph(c.canada_confirmed),
            last_seen=(c.last_seen_date or GLYPH_UNKNOWN)[:10],
            notes=c.notes or GLYPH_UNKNOWN,
            detail_text=_format_company_detail(c),
        )


def _format_posting_detail(p: Posting) -> str:
    """Mirror of tui/tui/widgets/jobs_panel.py::_format_details."""
    lines: list[str] = []
    if p.final_score is not None:
        modifier = p.modifier or 0
        base = p.base_score if p.base_score is not None else "?"
        lines.append(f"Score:    {p.final_score}  (base {base}, modifier {modifier:+d})")
    lines.append(f"Platform: {p.platform or '—'}")
    lines.append(f"Location: {p.location_note or '—'}")
    if p.employment_type:
        lines.append(f"Type:     {p.employment_type}")
    if p.post_date:
        lines.append(f"Posted:   {p.post_date}")
    if p.applicant_count is not None:
        lines.append(f"Applicants: {p.applicant_count}")
    lines.append(f"Status:   {p.status or '—'}")
    if p.description_summary:
        lines.extend(["", "Summary:", p.description_summary])
    if p.scoring_notes:
        lines.extend(["", "Scoring notes:", p.scoring_notes])
    lines.extend(["", f"URL: {p.url}"])
    return "\n".join(lines)


def _format_company_detail(c: Company) -> str:
    """Mirror of tui/tui/widgets/company_panel.py::_format_details."""
    lines: list[str] = [f"Company:  {c.name or '—'}"]
    lines.append(f"Remote:   {_bool_glyph(c.remote_confirmed)}")
    lines.append(f"Canada:   {_bool_glyph(c.canada_confirmed)}")
    if c.last_seen_date:
        lines.append(f"Last seen: {c.last_seen_date[:10]}")
    if c.researched_date:
        lines.append(f"Researched: {c.researched_date[:10]}")
    if c.careers_url:
        lines.append(f"Careers:  {c.careers_url}")
    if c.notes:
        lines.extend(["", "Notes:", c.notes])
    if c.fetch_notes:
        lines.extend(["", "Fetch notes:", c.fetch_notes])
    return "\n".join(lines)
