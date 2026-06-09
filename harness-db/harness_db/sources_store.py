"""Per-user job-search source selection, read from the DB.

Replaces ``$JOB_DATA_ROOT/jobs/sources-config.json``. The job-seeker reads the
enabled set from here (via the ``harness-db sources`` CLI); the TUI and web UI
edit it through :func:`set_enabled`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import get_active_uid
from harness_db.models import Source, UserSource
from harness_db.seed import ensure_schema_and_seed, ensure_user_defaults

__all__ = ["SourceSelection", "list_sources", "enabled_source_ids", "set_enabled"]


@dataclass(frozen=True)
class SourceSelection:
    source_id: str
    name: str
    description: str
    enabled: bool


@lru_cache(maxsize=1)
def _engine() -> Engine:
    # Stores assume migration already ran at a top-level entry point; here we only
    # guarantee the schema, default user, and default selection exist.
    return ensure_schema_and_seed(import_existing=False)


def _ensure_selection(session: Session, uid: str) -> None:
    """Make sure the user has a join row for every source (idempotent)."""
    ensure_user_defaults(session, uid)


def list_sources(uid: str | None = None) -> list[SourceSelection]:
    """All active sources with this user's enabled flag, ordered by source_id."""
    uid = uid or get_active_uid()
    engine = _engine()
    with Session(engine) as session:
        _ensure_selection(session, uid)
        session.commit()
        enabled = {
            r.source_id: r.enabled
            for r in session.scalars(select(UserSource).where(UserSource.uid == uid))
        }
        sources = session.scalars(
            select(Source).where(Source.active.is_(True)).order_by(Source.source_id)
        )
        return [
            SourceSelection(
                source_id=s.source_id,
                name=s.name or s.source_id,
                description=s.description or "",
                enabled=enabled.get(s.source_id, True),
            )
            for s in sources
        ]


def enabled_source_ids(uid: str | None = None) -> list[str]:
    """The source ids this user has enabled (active sources only)."""
    return [s.source_id for s in list_sources(uid) if s.enabled]


def set_enabled(source_id: str, enabled: bool, uid: str | None = None) -> None:
    """Toggle a source for the user (upserts the join row)."""
    uid = uid or get_active_uid()
    engine = _engine()
    with Session(engine) as session:
        row = session.scalar(
            select(UserSource).where(UserSource.uid == uid, UserSource.source_id == source_id)
        )
        if row is None:
            session.add(UserSource(uid=uid, source_id=source_id, enabled=enabled))
        else:
            row.enabled = enabled
        session.commit()
