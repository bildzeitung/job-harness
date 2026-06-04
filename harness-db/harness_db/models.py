"""Shared SQLAlchemy models for the job-harness DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import (
    Boolean,
    Engine,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from harness_db.embeddings import EMBED_DIM

# Milliseconds SQLite waits on a locked DB before raising, so concurrent writers
# (web app, TUI, pipeline) retry instead of failing immediately.
_BUSY_TIMEOUT_MS = 5000


class Base(DeclarativeBase):
    pass


class Posting(Base):
    __tablename__ = "postings"

    url: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str | None] = mapped_column(String)
    company: Mapped[str | None] = mapped_column(String)
    platform: Mapped[str | None] = mapped_column(String)
    post_date: Mapped[str | None] = mapped_column(String)
    location_note: Mapped[str | None] = mapped_column(String)
    description_summary: Mapped[str | None] = mapped_column(String)
    first_seen: Mapped[str | None] = mapped_column(String)
    scored_date: Mapped[str | None] = mapped_column(String)
    base_score: Mapped[int | None] = mapped_column(Integer)
    modifier: Mapped[int | None] = mapped_column(Integer)
    final_score: Mapped[int | None] = mapped_column(Integer)
    scoring_notes: Mapped[str | None] = mapped_column(String)
    dimension_scores: Mapped[str | None] = mapped_column(String)
    job_description_text: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String)
    selected_date: Mapped[str | None] = mapped_column(String)
    employment_type: Mapped[str | None] = mapped_column(String)
    applicant_count: Mapped[int | None] = mapped_column(Integer)

    @property
    def display_name(self) -> str:
        parts = [p for p in (self.company, self.title) if p]
        return " · ".join(parts) if parts else self.url

    @property
    def display_date(self) -> str:
        if not self.first_seen:
            return "—"
        return self.first_seen[:10].replace("-", "/")


class Company(Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    notes: Mapped[str | None] = mapped_column(Text)
    remote_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    canada_confirmed: Mapped[bool | None] = mapped_column(Boolean)
    researched_date: Mapped[str | None] = mapped_column(String)
    last_seen_date: Mapped[str | None] = mapped_column(String)
    careers_url: Mapped[str | None] = mapped_column(String)
    fetch_notes: Mapped[str | None] = mapped_column(Text)


class CompanyPosting(Base):
    """Links each posting to its hiring company (1 company : N postings)."""

    __tablename__ = "company_postings"

    url: Mapped[str] = mapped_column(String, ForeignKey("postings.url"), primary_key=True)
    company_name: Mapped[str] = mapped_column(String, ForeignKey("companies.name"))

    __table_args__ = (Index("ix_company_postings_company_name", "company_name"),)


def make_engine(db_path: Path) -> Engine:
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            # busy_timeout retries on locks; harmless on read-only databases.
            cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
            # WAL lets readers and a writer coexist. Best-effort: switching journal
            # mode needs write access, so skip it for a read-only DB rather than fail.
            cursor.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        finally:
            cursor.close()
        _load_sqlite_vec(dbapi_connection)

    return engine


def _load_sqlite_vec(dbapi_connection) -> None:
    """Load the sqlite-vec extension and ensure ``postings_vec`` exists.

    The semantic layer is a required part of the harness: callers are assumed to
    meet the prerequisites (an extension-capable Python build plus the sqlite-vec
    package), so a missing capability is a configuration error we surface loudly
    rather than silently degrade. Only table creation is tolerant — a read-only
    consumer still loads the extension and queries an existing ``postings_vec``,
    it just can't create one.
    """
    import sqlite_vec  # required dependency; ImportError means prerequisites unmet

    if not hasattr(dbapi_connection, "enable_load_extension"):
        raise RuntimeError(
            "This Python's sqlite3 was built without loadable-extension support, "
            "which the harness requires. Rebuild Python with "
            "--enable-loadable-sqlite-extensions (e.g. via "
            'PYTHON_CONFIGURE_OPTS="--enable-loadable-sqlite-extensions" pyenv install).'
        )

    dbapi_connection.enable_load_extension(True)
    sqlite_vec.load(dbapi_connection)
    dbapi_connection.enable_load_extension(False)
    try:
        dbapi_connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS postings_vec USING vec0("
            f"url TEXT PRIMARY KEY, embedding float[{EMBED_DIM}] distance_metric=cosine)"
        )
    except sqlite3.OperationalError:
        # Read-only DB: extension is loaded for querying, but we can't CREATE.
        pass
