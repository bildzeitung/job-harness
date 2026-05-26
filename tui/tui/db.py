from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_db.models import Posting, make_engine  # noqa: F401 — re-exported for callers

__all__ = ["Posting", "make_engine", "get_postings"]


def get_postings(engine) -> list[Posting]:
    stmt = select(Posting).order_by(Posting.first_seen.desc())
    with Session(engine) as session:
        return list(session.scalars(stmt))
