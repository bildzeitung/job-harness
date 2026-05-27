from __future__ import annotations

from harness_db.models import Company, Posting, make_engine  # noqa: F401 — re-exported for callers
from sqlalchemy import select
from sqlalchemy.orm import Session

__all__ = ["Company", "Posting", "make_engine", "get_postings", "get_companies", "update_status"]

_STATE_ORDER = {"selected": 0, "scored": 1, "new": 2, "applied": 3, "skipped": 4}


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
        postings.sort(key=lambda p: _STATE_ORDER.get(p.status or "new", 99))
    return postings


def get_postings(engine, sort_by: str = "state") -> list[Posting]:
    with Session(engine) as session:
        postings = list(session.scalars(select(Posting)))
    return _sort_postings(postings, sort_by)


def get_companies(engine) -> list[Company]:
    with Session(engine) as session:
        return list(session.scalars(select(Company).order_by(Company.name)))


def update_status(engine, url: str, status: str) -> None:
    with Session(engine) as session:
        posting = session.get(Posting, url)
        if posting is not None:
            posting.status = status
            session.commit()
