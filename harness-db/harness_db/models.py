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


# ── Multi-user configuration (spec 12, phase 1) ───────────────────────────────
#
# All user-facing inputs become data-driven and per-user. The pattern throughout
# is "catalog + per-user selection": a catalog table holds the available items
# (built-in rows have ``owner_uid`` NULL; a user's custom additions carry their
# uid), and a ``user_*`` join table records which a given user has enabled. This
# phase scopes ONLY configuration — postings/companies/scoring stay shared.


class User(Base):
    __tablename__ = "users"

    uid: Mapped[str] = mapped_column(String, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[str | None] = mapped_column(String)


class ConfigItem(Base):
    """Catalog of known config keys (e.g. RESUME_FILE, ADZUNA_APP_ID)."""

    __tablename__ = "config_items"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)


class UserConfigItem(Base):
    """A user's value for one config key."""

    __tablename__ = "user_config_items"

    uid: Mapped[str] = mapped_column(String, ForeignKey("users.uid"), primary_key=True)
    config_key: Mapped[str] = mapped_column(
        String, ForeignKey("config_items.key"), primary_key=True
    )
    value: Mapped[str | None] = mapped_column(String)


class Source(Base):
    """Catalog of high-level job-search sources (the job-seeker's 7 platforms)."""

    __tablename__ = "sources"

    source_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSource(Base):
    """Whether a user has a given source enabled for their searches."""

    __tablename__ = "user_sources"

    uid: Mapped[str] = mapped_column(String, ForeignKey("users.uid"), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String, ForeignKey("sources.source_id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class PrefilterRule(Base):
    """One hard prefilter rule. ``category`` is one of the disqualifier sections:
    description_phrases, title_terms, title_terms_unless_senior, seniority_exceptions."""

    __tablename__ = "prefilter_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(String)
    owner_uid: Mapped[str | None] = mapped_column(String, ForeignKey("users.uid"))


class UserPrefilterRule(Base):
    __tablename__ = "user_prefilter_rules"

    uid: Mapped[str] = mapped_column(String, ForeignKey("users.uid"), primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("prefilter_rules.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class ScoringModifierBlock(Base):
    """A named scoring-modifier block the scorer LLM applies (``examples`` is JSON)."""

    __tablename__ = "scoring_modifier_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String)
    modifier: Mapped[int] = mapped_column(Integer)
    examples: Mapped[str | None] = mapped_column(Text)
    owner_uid: Mapped[str | None] = mapped_column(String, ForeignKey("users.uid"))


class UserScoringModifier(Base):
    __tablename__ = "user_scoring_modifiers"

    uid: Mapped[str] = mapped_column(String, ForeignKey("users.uid"), primary_key=True)
    block_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scoring_modifier_blocks.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class TargetRoleItem(Base):
    """A target-role entry. ``kind`` is one of: title, keyword, domain."""

    __tablename__ = "target_role_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)
    value: Mapped[str] = mapped_column(String)
    owner_uid: Mapped[str | None] = mapped_column(String, ForeignKey("users.uid"))


class UserTargetRole(Base):
    __tablename__ = "user_target_roles"

    uid: Mapped[str] = mapped_column(String, ForeignKey("users.uid"), primary_key=True)
    item_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("target_role_items.id"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


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
