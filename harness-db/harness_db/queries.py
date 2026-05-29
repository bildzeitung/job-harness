"""Shared read/write query helpers for the job-harness DB.

Promoted out of the TUI so the TUI, the web app, and any other front-end share a
single implementation of posting/company access and sort ordering.
"""

from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.models import Company, Posting

__all__ = [
    "STATE_ORDER",
    "get_postings",
    "get_companies",
    "get_company_postings",
    "update_status",
]

# Sort priority for the default "state" ordering. Lower sorts first.
STATE_ORDER: dict[str, int] = {
    "prepared": 0,
    "selected": 1,
    "scored": 2,
    "new": 3,
    "applied": 4,
    "rejected": 5,
    "skipped": 6,
}

# Fallback priority for any status not present in STATE_ORDER.
_UNKNOWN_STATE_PRIORITY = 99


def _sort_postings(postings: list[Posting], sort_by: str) -> list[Posting]:
    if sort_by == "date":
        postings.sort(key=lambda p: (p.title or "").lower())
        postings.sort(key=lambda p: p.first_seen or "", reverse=True)
    elif sort_by == "title":
        postings.sort(key=lambda p: p.first_seen or "", reverse=True)
        postings.sort(key=lambda p: (p.title or "").lower())
    else:  # "state" (default): state priority, then date desc, then title asc
        postings.sort(key=lambda p: (p.title or "").lower())
        postings.sort(key=lambda p: p.first_seen or "", reverse=True)
        postings.sort(key=lambda p: STATE_ORDER.get(p.status or "new", _UNKNOWN_STATE_PRIORITY))
    return postings


def get_postings(engine: Engine, sort_by: str = "state") -> list[Posting]:
    with Session(engine) as session:
        postings = list(session.scalars(select(Posting)))
    return _sort_postings(postings, sort_by)


def get_companies(engine: Engine) -> list[Company]:
    with Session(engine) as session:
        return list(session.scalars(select(Company).order_by(Company.name)))


def get_company_postings(engine: Engine, company_name: str) -> list[Posting]:
    """All postings for a company (matched by stored company name).

    Ordered best-fit first: highest final_score (unscored last), then most
    recently seen, then title.
    """
    with Session(engine) as session:
        postings = list(session.scalars(select(Posting).where(Posting.company == company_name)))
    postings.sort(key=lambda p: (p.title or "").lower())
    postings.sort(key=lambda p: p.first_seen or "", reverse=True)
    postings.sort(key=lambda p: (p.final_score is None, -(p.final_score or 0)))
    return postings


def update_status(engine: Engine, url: str, status: str) -> None:
    with Session(engine) as session:
        posting = session.get(Posting, url)
        if posting is not None:
            posting.status = status
            session.commit()
