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

# Exceptions we treat as "vector layer unavailable, carry on" when loading
# sqlite-vec. AttributeError covers a stdlib sqlite3 with no enable_load_extension;
# OperationalError covers a read-only DB. pysqlite3 defines its own OperationalError
# class distinct from the stdlib one, so include it when present.
_VEC_SKIP_EXC: tuple[type[Exception], ...] = (sqlite3.OperationalError, AttributeError)
try:
    from pysqlite3 import dbapi2 as _pysqlite3_dbapi

    _VEC_SKIP_EXC += (_pysqlite3_dbapi.OperationalError,)
except ImportError:
    pass


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


def _extension_capable_sqlite_module():
    """Return a DBAPI module whose connections can load SQLite extensions, or None.

    Many Python builds (e.g. CPython 3.14 here) ship a stdlib ``sqlite3`` compiled
    without ``--enable-loadable-sqlite-extensions``, so ``enable_load_extension`` is
    absent and sqlite-vec cannot be loaded. ``pysqlite3-binary`` bundles its own
    SQLite with extensions enabled and is a drop-in DBAPI. We only reach for it when
    the stdlib can't do the job and it's installed (it ships in the ``semantic``
    extra); otherwise return None and let SQLAlchemy use the stdlib driver, leaving
    non-semantic installs byte-for-byte unchanged.
    """
    if hasattr(sqlite3.Connection, "enable_load_extension"):
        return None
    try:
        from pysqlite3 import dbapi2 as pysqlite3_dbapi
    except ImportError:
        return None
    return pysqlite3_dbapi


def make_engine(db_path: Path) -> Engine:
    module = _extension_capable_sqlite_module()
    engine = (
        create_engine(f"sqlite:///{db_path}", echo=False, module=module)
        if module is not None
        else create_engine(f"sqlite:///{db_path}", echo=False)
    )

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
    """Best-effort: load the sqlite-vec extension and ensure ``postings_vec`` exists.

    Optional and fully guarded — a harness installed without the ``semantic``
    extra (no ``sqlite_vec``), a Python built without extension loading, or a
    read-only DB all fall through silently and leave existing behaviour untouched.
    The vector table is a sidecar keyed by ``Posting.url``; it carries no foreign
    key, so a missing row simply means "not embedded yet".
    """
    try:
        import sqlite_vec
    except ImportError:
        return
    try:
        dbapi_connection.enable_load_extension(True)
        sqlite_vec.load(dbapi_connection)
        dbapi_connection.enable_load_extension(False)
        dbapi_connection.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS postings_vec USING vec0("
            f"url TEXT PRIMARY KEY, embedding float[{EMBED_DIM}] distance_metric=cosine)"
        )
    except _VEC_SKIP_EXC:
        # Read-only DB, or sqlite3 compiled without enable_load_extension — skip.
        pass
