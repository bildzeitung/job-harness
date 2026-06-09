"""Load and apply the harness's hard disqualifiers.

Disqualifiers are **data-driven and per-user**, stored in the harness DB:

* ``prefilter`` — keyword rules applied as EARLY as possible (at search time by
  every source, and again by ``job-preparer`` before scoring) to drop noise
  before it costs anything.
* ``scoring_modifiers`` — negative score modifiers the scorer LLM applies during
  scoring.

The loaders read the active user's enabled rules from the DB. For backward
compatibility — an install whose DB has not been created yet — they fall back to
the legacy ``$JOB_DATA_ROOT/disqualifiers.yaml`` file (seeding it from the bundled
default on first read). The pure matcher :func:`prefilter_disqualifies` is the
single shared predicate every source and ``job-preparer`` use.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import get_active_uid, get_db_path, get_job_data_root
from harness_db.models import (
    PrefilterRule,
    ScoringModifierBlock,
    UserPrefilterRule,
    UserScoringModifier,
    make_engine,
)
from harness_db.seed import PREFILTER_CATEGORIES, ensure_schema_and_seed, ensure_user_defaults

__all__ = [
    "load_disqualifiers",
    "load_prefilter",
    "prefilter_disqualifies",
    "PrefilterRuleView",
    "ScoringBlockView",
    "list_prefilter_rules",
    "set_prefilter_enabled",
    "add_prefilter_rule",
    "delete_prefilter_rule",
    "list_scoring_blocks",
    "set_scoring_enabled",
    "add_scoring_block",
    "delete_scoring_block",
]

_FILENAME = "disqualifiers.yaml"
_DEFAULT_TEMPLATE = Path(__file__).with_name("disqualifiers.default.yaml")


# ── engine helpers ────────────────────────────────────────────────────────────


@lru_cache(maxsize=8)
def _engine_for(db_path_str: str) -> Engine:
    return make_engine(db_path_str)


def _ro_engine() -> Engine | None:
    """Engine for the DB if it already exists (read path never creates one)."""
    try:
        db_path = get_db_path()
    except RuntimeError:
        return None
    return _engine_for(str(db_path)) if db_path.exists() else None


def _rw_engine() -> Engine:
    """Seeded engine for interactive edits (creates schema + defaults if needed).

    Reuses the cached engine for the resolved DB path so repeated edits don't
    rebuild the connection pool / reload the sqlite-vec extension each call; the
    seed itself is idempotent and cheap on an already-seeded DB.
    """
    return ensure_schema_and_seed(_engine_for(str(get_db_path())), import_existing=False)


# ── public loaders (DB → file fallback) ───────────────────────────────────────


def load_disqualifiers(uid: str | None = None) -> dict[str, Any]:
    """Effective disqualifiers for the user: ``{prefilter, scoring_modifiers}``."""
    db = _db_disqualifiers(uid)
    return db if db is not None else _file_disqualifiers()


def load_prefilter(uid: str | None = None) -> dict[str, Any]:
    """Just the ``prefilter`` section of the effective disqualifiers."""
    return load_disqualifiers(uid).get("prefilter", {}) or {}


def _db_disqualifiers(uid: str | None) -> dict[str, Any] | None:
    engine = _ro_engine()
    if engine is None:
        return None
    uid = uid or get_active_uid()
    try:
        with Session(engine) as session:
            prefilter: dict[str, list[str]] = {c: [] for c in PREFILTER_CATEGORIES}
            rules = session.execute(
                select(PrefilterRule)
                .join(UserPrefilterRule, UserPrefilterRule.rule_id == PrefilterRule.id)
                .where(UserPrefilterRule.uid == uid, UserPrefilterRule.enabled.is_(True))
            ).scalars()
            for r in rules:
                prefilter.setdefault(r.category, []).append(r.value)

            blocks = session.execute(
                select(ScoringModifierBlock)
                .join(
                    UserScoringModifier,
                    UserScoringModifier.block_id == ScoringModifierBlock.id,
                )
                .where(UserScoringModifier.uid == uid, UserScoringModifier.enabled.is_(True))
            ).scalars()
            scoring_modifiers = [
                {
                    "name": b.name,
                    "modifier": b.modifier,
                    "examples": json.loads(b.examples) if b.examples else [],
                }
                for b in blocks
            ]
        return {"prefilter": prefilter, "scoring_modifiers": scoring_modifiers}
    except Exception:
        return None


def _file_disqualifiers() -> dict[str, Any]:
    """Legacy file source: ``$JOB_DATA_ROOT/disqualifiers.yaml`` (seeded if absent)."""
    live = get_job_data_root() / _FILENAME
    if not live.exists():
        live.write_text(_DEFAULT_TEMPLATE.read_text())
    with open(live) as f:
        return yaml.safe_load(f) or {}


# ── pure matcher (unchanged shared predicate) ─────────────────────────────────


def prefilter_disqualifies(title: str, text: str, prefilter: dict[str, Any]) -> bool:
    """True if a posting matches any hard prefilter rule (case-insensitive).

    Implements the canonical semantics shared by every source and by
    ``job-preparer``:

    * ``description_phrases`` — any phrase appears in the title or description.
    * ``title_terms`` — any term appears in the title.
    * ``title_terms_unless_senior`` — any term appears in the title, UNLESS the
      title also contains a ``seniority_exceptions`` term (e.g. "senior",
      "staff", "principal" — seniority qualifiers, not contradictions).
    """
    title_l = title.lower()
    combined_l = f"{title} {text}".lower()

    for phrase in prefilter.get("description_phrases", []):
        if phrase.lower() in combined_l:
            return True

    for term in prefilter.get("title_terms", []):
        if term.lower() in title_l:
            return True

    seniority_exceptions = [s.lower() for s in prefilter.get("seniority_exceptions", [])]
    has_seniority = any(s in title_l for s in seniority_exceptions)
    if not has_seniority:
        for term in prefilter.get("title_terms_unless_senior", []):
            if term.lower() in title_l:
                return True

    return False


# ── CRUD for the TUI / web / CLI ──────────────────────────────────────────────


@dataclass(frozen=True)
class PrefilterRuleView:
    id: int
    category: str
    value: str
    enabled: bool
    custom: bool


@dataclass(frozen=True)
class ScoringBlockView:
    id: int
    name: str
    modifier: int
    examples: list[str]
    enabled: bool
    custom: bool


def list_prefilter_rules(uid: str | None = None) -> list[PrefilterRuleView]:
    """All prefilter rules visible to the user (built-ins + own), with enabled flag."""
    uid = uid or get_active_uid()
    engine = _rw_engine()
    with Session(engine) as session:
        ensure_user_defaults(session, uid)
        session.commit()
        enabled = {
            r.rule_id: r.enabled
            for r in session.scalars(select(UserPrefilterRule).where(UserPrefilterRule.uid == uid))
        }
        rules = session.scalars(
            select(PrefilterRule)
            .where((PrefilterRule.owner_uid.is_(None)) | (PrefilterRule.owner_uid == uid))
            .order_by(PrefilterRule.category, PrefilterRule.value)
        )
        return [
            PrefilterRuleView(
                id=r.id,
                category=r.category,
                value=r.value,
                enabled=enabled.get(r.id, False),
                custom=r.owner_uid == uid,
            )
            for r in rules
        ]


def set_prefilter_enabled(rule_id: int, enabled: bool, uid: str | None = None) -> None:
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        row = session.scalar(
            select(UserPrefilterRule).where(
                UserPrefilterRule.uid == uid, UserPrefilterRule.rule_id == rule_id
            )
        )
        if row is None:
            session.add(UserPrefilterRule(uid=uid, rule_id=rule_id, enabled=enabled))
        else:
            row.enabled = enabled
        session.commit()


def add_prefilter_rule(category: str, value: str, uid: str | None = None) -> int:
    """Add a custom prefilter rule for the user (enabled). Returns the new rule id."""
    if category not in PREFILTER_CATEGORIES:
        raise ValueError(f"Unknown prefilter category {category!r}")
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        rule = PrefilterRule(category=category, value=value, owner_uid=uid)
        session.add(rule)
        session.flush()
        session.add(UserPrefilterRule(uid=uid, rule_id=rule.id, enabled=True))
        session.commit()
        return rule.id


def delete_prefilter_rule(rule_id: int, uid: str | None = None) -> None:
    """Delete a custom rule the user owns (built-ins can only be disabled)."""
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        rule = session.get(PrefilterRule, rule_id)
        if rule is None:
            return
        if rule.owner_uid != uid:
            raise ValueError("Only custom rules you own can be deleted; disable built-ins instead.")
        session.execute(
            UserPrefilterRule.__table__.delete().where(
                UserPrefilterRule.uid == uid, UserPrefilterRule.rule_id == rule_id
            )
        )
        session.delete(rule)
        session.commit()


def list_scoring_blocks(uid: str | None = None) -> list[ScoringBlockView]:
    uid = uid or get_active_uid()
    engine = _rw_engine()
    with Session(engine) as session:
        ensure_user_defaults(session, uid)
        session.commit()
        enabled = {
            r.block_id: r.enabled
            for r in session.scalars(
                select(UserScoringModifier).where(UserScoringModifier.uid == uid)
            )
        }
        blocks = session.scalars(
            select(ScoringModifierBlock)
            .where(
                (ScoringModifierBlock.owner_uid.is_(None)) | (ScoringModifierBlock.owner_uid == uid)
            )
            .order_by(ScoringModifierBlock.name)
        )
        return [
            ScoringBlockView(
                id=b.id,
                name=b.name,
                modifier=b.modifier,
                examples=json.loads(b.examples) if b.examples else [],
                enabled=enabled.get(b.id, False),
                custom=b.owner_uid == uid,
            )
            for b in blocks
        ]


def set_scoring_enabled(block_id: int, enabled: bool, uid: str | None = None) -> None:
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        row = session.scalar(
            select(UserScoringModifier).where(
                UserScoringModifier.uid == uid, UserScoringModifier.block_id == block_id
            )
        )
        if row is None:
            session.add(UserScoringModifier(uid=uid, block_id=block_id, enabled=enabled))
        else:
            row.enabled = enabled
        session.commit()


def add_scoring_block(
    name: str, modifier: int, examples: list[str] | None = None, uid: str | None = None
) -> int:
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        block = ScoringModifierBlock(
            name=name,
            modifier=modifier,
            examples=json.dumps(examples or []),
            owner_uid=uid,
        )
        session.add(block)
        session.flush()
        session.add(UserScoringModifier(uid=uid, block_id=block.id, enabled=True))
        session.commit()
        return block.id


def delete_scoring_block(block_id: int, uid: str | None = None) -> None:
    uid = uid or get_active_uid()
    with Session(_rw_engine()) as session:
        block = session.get(ScoringModifierBlock, block_id)
        if block is None:
            return
        if block.owner_uid != uid:
            raise ValueError(
                "Only custom blocks you own can be deleted; disable built-ins instead."
            )
        session.execute(
            UserScoringModifier.__table__.delete().where(
                UserScoringModifier.uid == uid, UserScoringModifier.block_id == block_id
            )
        )
        session.delete(block)
        session.commit()
