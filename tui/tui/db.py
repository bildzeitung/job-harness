from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_db.models import Posting, make_engine  # noqa: F401 — re-exported for callers

__all__ = ["Posting", "make_engine", "get_postings", "update_status"]


def get_postings(engine) -> list[Posting]:
    stmt = select(Posting).order_by(Posting.first_seen.desc())
    with Session(engine) as session:
        return list(session.scalars(stmt))


def update_status(engine, url: str, status: str) -> None:
    with Session(engine) as session:
        posting = session.get(Posting, url)
        if posting is not None:
            posting.status = status
            session.commit()
