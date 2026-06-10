"""Create the multi-user config schema and seed it (spec 12, phase 1).

``ensure_schema_and_seed`` is the single startup entry point every front-end and
the migration script call. It is idempotent:

1. Creates all tables.
2. Ensures the built-in catalogs exist (config keys, the 7 sources, the default
   prefilter rules, scoring-modifier blocks, and target-role items).
3. Ensures the ``default`` user exists with every built-in enabled.
4. **On the first run only** (when the default user did not yet exist), imports
   any existing on-disk config — ``sources-config.json``,
   ``disqualifiers.yaml``, ``target-roles.md`` and the env config values — into
   the default user so an existing single-user install migrates seamlessly.

Re-running never clobbers user edits: catalog seeding only inserts missing rows,
default selection only inserts missing join rows (it never flips an existing
``enabled`` flag), and the file import runs once.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import DEFAULT_UID, _env_or_settings, get_db_path, get_job_data_root
from harness_db.models import (
    Base,
    ConfigItem,
    PrefilterRule,
    ScoringModifierBlock,
    Source,
    TargetRoleItem,
    User,
    UserConfigItem,
    UserPrefilterRule,
    UserScoringModifier,
    UserSource,
    UserTargetRole,
    make_engine,
)
from harness_db.users import _now

_HERE = Path(__file__).parent
_DISQUALIFIERS_DEFAULT = _HERE / "disqualifiers.default.yaml"
_TARGET_ROLES_DEFAULT = _HERE / "target-roles.default.yaml"

PREFILTER_CATEGORIES = (
    "description_phrases",
    "title_terms",
    "title_terms_unless_senior",
    "seniority_exceptions",
)

# The 7 high-level job-search sources the job-seeker orchestrator fans out to.
# Kept in sync with the job-search skill / job-seeker agent (see the
# "Sources table" maintenance memory).
BUILTIN_SOURCES: list[dict[str, str]] = [
    {
        "source_id": "linkedin",
        "name": "LinkedIn",
        "description": "LinkedIn (MCP, needs active browser session)",
    },
    {"source_id": "indeed", "name": "Indeed", "description": "Indeed (MCP)"},
    {"source_id": "adzuna", "name": "Adzuna", "description": "Adzuna Canada (REST API)"},
    {"source_id": "ziprecruiter", "name": "ZipRecruiter", "description": "ZipRecruiter (MCP)"},
    {
        "source_id": "greenhouse",
        "name": "ATS boards",
        "description": "Greenhouse.io + Lever.co + Ashby + Workable + Recruitee public ATS APIs",
    },
    {
        "source_id": "remotive",
        "name": "Remote boards",
        "description": "Remotive + Himalayas + We Work Remotely remote-jobs boards (Canada-eligible)",
    },
    {
        "source_id": "research",
        "name": "Research",
        "description": "Non-job-board: Wellfound, funded startups, niche boards, Canada boards",
    },
]

BUILTIN_CONFIG_ITEMS: list[dict[str, str]] = [
    {
        "key": "JOB_DATA_ROOT",
        "name": "Job data root",
        "description": "Directory for job data and outputs.",
    },
    {
        "key": "RESUME_FILE",
        "name": "Resume file",
        "description": "Absolute path to the RenderCV CV YAML.",
    },
    {"key": "ADZUNA_APP_ID", "name": "Adzuna app ID", "description": "Adzuna API application id."},
    {"key": "ADZUNA_API_KEY", "name": "Adzuna API key", "description": "Adzuna API key."},
    {
        "key": "JOB_TOP_N",
        "name": "Top N postings",
        "description": "How many top-ranked postings job-preparer's score phase returns (default 5).",
    },
    # Candidate-summary judgment fields (spec 14 A4): the deterministic
    # `harness-db candidate-summary` command reads these instead of an LLM
    # re-inventing them daily. Edit them in Settings → Config.
    {
        "key": "CANDIDATE_HEADLINE",
        "name": "Candidate headline",
        "description": "One-line professional identity, e.g. 'Principal Engineer — Cloud, AI'.",
    },
    {
        "key": "CANDIDATE_NOTABLE",
        "name": "Candidate notable",
        "description": "A standout credential, e.g. '13 years at Oracle (OCI, Health & AI)'.",
    },
    {
        "key": "CANDIDATE_YEARS_EXPERIENCE",
        "name": "Years of experience",
        "description": "Total years of professional experience (integer).",
    },
    {
        "key": "CANDIDATE_WORK_TYPE",
        "name": "Work type",
        "description": "Desired work type (default 'fully remote').",
    },
    {
        "key": "CANDIDATE_ELIGIBILITY",
        "name": "Work eligibility",
        "description": "Eligibility note for the scorer (default 'Canada-eligible').",
    },
    {
        "key": "CANDIDATE_EMPLOYMENT",
        "name": "Employment types",
        "description": "Comma-separated (default 'full-time,contract,freelance').",
    },
    {
        "key": "CANDIDATE_COMP_FLOOR_CAD",
        "name": "Compensation floor (CAD)",
        "description": "Optional minimum acceptable annual compensation in CAD (integer).",
    },
]


def ensure_schema_and_seed(engine: Engine | None = None, import_existing: bool = True) -> Engine:
    """Create the config schema and seed catalogs + the default user (idempotent)."""
    engine = engine or make_engine(get_db_path())
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        _seed_config_items(session)
        _seed_sources(session)
        _seed_prefilter_catalog(session)
        _seed_scoring_catalog(session)
        _seed_target_role_catalog(session)
        first_run = _ensure_default_user(session)
        ensure_user_defaults(session, DEFAULT_UID)
        session.commit()
        if first_run and import_existing:
            _import_existing(session, DEFAULT_UID)
            session.commit()
    return engine


# ── catalog seeding (insert-missing only) ─────────────────────────────────────


def _seed_config_items(session: Session) -> None:
    existing = set(session.scalars(select(ConfigItem.key)))
    for item in BUILTIN_CONFIG_ITEMS:
        if item["key"] not in existing:
            session.add(ConfigItem(**item))


def _seed_sources(session: Session) -> None:
    existing = set(session.scalars(select(Source.source_id)))
    for src in BUILTIN_SOURCES:
        if src["source_id"] not in existing:
            session.add(Source(active=True, **src))


def _seed_prefilter_catalog(session: Session) -> None:
    # Seed built-ins only once: skip if any built-in (owner_uid NULL) row exists.
    if session.scalar(select(PrefilterRule.id).where(PrefilterRule.owner_uid.is_(None)).limit(1)):
        return
    with open(_DISQUALIFIERS_DEFAULT) as f:
        data = yaml.safe_load(f) or {}
    prefilter = data.get("prefilter", {}) or {}
    for category in PREFILTER_CATEGORIES:
        for value in prefilter.get(category, []) or []:
            session.add(PrefilterRule(category=category, value=value, owner_uid=None))


def _seed_scoring_catalog(session: Session) -> None:
    if session.scalar(
        select(ScoringModifierBlock.id).where(ScoringModifierBlock.owner_uid.is_(None)).limit(1)
    ):
        return
    with open(_DISQUALIFIERS_DEFAULT) as f:
        data = yaml.safe_load(f) or {}
    for block in data.get("scoring_modifiers", []) or []:
        session.add(
            ScoringModifierBlock(
                name=block.get("name", ""),
                modifier=int(block.get("modifier", 0)),
                examples=json.dumps(block.get("examples", []) or []),
                owner_uid=None,
            )
        )


def _seed_target_role_catalog(session: Session) -> None:
    if session.scalar(select(TargetRoleItem.id).where(TargetRoleItem.owner_uid.is_(None)).limit(1)):
        return
    with open(_TARGET_ROLES_DEFAULT) as f:
        data = yaml.safe_load(f) or {}
    for kind, key in (("title", "titles"), ("keyword", "keywords"), ("domain", "domains")):
        for value in data.get(key, []) or []:
            session.add(TargetRoleItem(kind=kind, value=value, owner_uid=None))


# ── default user + default selection ──────────────────────────────────────────


def _ensure_default_user(session: Session) -> bool:
    """Ensure the default user exists. Returns True if it was just created."""
    if session.get(User, DEFAULT_UID) is not None:
        return False
    session.add(User(uid=DEFAULT_UID, active=True, created_at=_now()))
    return True


def ensure_user_defaults(session: Session, uid: str) -> None:
    """Enable every built-in catalog item for ``uid`` (insert-missing join rows).

    Never flips an existing ``enabled`` flag, so a user's later toggles survive
    and only newly-added built-ins get turned on by default.
    """
    _select_all_missing(session, uid, Source, "source_id", UserSource, "source_id", scoped=False)
    _select_all_missing(
        session, uid, PrefilterRule, "id", UserPrefilterRule, "rule_id", scoped=True
    )
    _select_all_missing(
        session, uid, ScoringModifierBlock, "id", UserScoringModifier, "block_id", scoped=True
    )
    _select_all_missing(session, uid, TargetRoleItem, "id", UserTargetRole, "item_id", scoped=True)


def _select_all_missing(session, uid, catalog_model, catalog_pk, join_model, join_fk, scoped):
    """Insert an enabled join row for every catalog item the user has no row for.

    ``scoped`` restricts the catalog to built-ins (owner_uid NULL) plus the user's
    own custom rows — used for catalogs that carry ``owner_uid``.
    """
    catalog_col = getattr(catalog_model, catalog_pk)
    stmt = select(catalog_col)
    if scoped:
        stmt = stmt.where((catalog_model.owner_uid.is_(None)) | (catalog_model.owner_uid == uid))
    catalog_ids = set(session.scalars(stmt))
    have = set(session.scalars(select(getattr(join_model, join_fk)).where(join_model.uid == uid)))
    for cid in catalog_ids - have:
        session.add(join_model(uid=uid, enabled=True, **{join_fk: cid}))


# ── one-time file import (first run only) ─────────────────────────────────────


def _import_existing(session: Session, uid: str) -> None:
    try:
        data_root = get_job_data_root()
    except RuntimeError:
        data_root = None
    if data_root is not None:
        _import_sources(session, uid, data_root / "jobs" / "sources-config.json")
        _import_disqualifiers(session, uid, data_root / "disqualifiers.yaml")
        _import_target_roles(session, uid, data_root / "target-roles.md")
        _import_candidate_fields(session, uid, data_root / "candidate-summary.json")
    _import_config(session, uid)


def _import_sources(session: Session, uid: str, path: Path) -> None:
    if not path.exists():
        return
    try:
        enabled = set(json.loads(path.read_text()).get("enabled", []))
    except ValueError:
        return
    for row in session.scalars(select(UserSource).where(UserSource.uid == uid)):
        row.enabled = row.source_id in enabled


def _import_disqualifiers(session: Session, uid: str, path: Path) -> None:
    if not path.exists():
        return
    with open(path) as f:
        data = yaml.safe_load(f) or {}

    # Prefilter rules: enable those present (find/create), disable built-ins absent.
    prefilter = data.get("prefilter", {}) or {}
    wanted_rule_ids: set[int] = set()
    for category in PREFILTER_CATEGORIES:
        for value in prefilter.get(category, []) or []:
            rule = _find_or_create_prefilter(session, uid, category, value)
            wanted_rule_ids.add(rule.id)
    _apply_selection(session, uid, UserPrefilterRule, "rule_id", wanted_rule_ids)

    # Scoring-modifier blocks: match built-ins by name; create custom otherwise.
    wanted_block_ids: set[int] = set()
    for block in data.get("scoring_modifiers", []) or []:
        b = _find_or_create_block(session, uid, block)
        wanted_block_ids.add(b.id)
    _apply_selection(session, uid, UserScoringModifier, "block_id", wanted_block_ids)


def _import_target_roles(session: Session, uid: str, path: Path) -> None:
    if not path.exists():
        return
    parsed = _parse_target_roles_md(path.read_text())
    wanted_ids: set[int] = set()
    for kind, values in parsed.items():
        for value in values:
            item = _find_or_create_target_role(session, uid, kind, value)
            wanted_ids.add(item.id)
    _apply_selection(session, uid, UserTargetRole, "item_id", wanted_ids)


def _import_candidate_fields(session: Session, uid: str, path: Path) -> None:
    """Seed candidate-summary judgment fields from an existing file (first run only).

    Maps the LLM-synthesised ``candidate-summary.json`` fields onto the new
    per-user config keys so an existing install migrates with zero typing. Only
    fills keys the user has not already set.
    """
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return
    req = data.get("requirements", {}) or {}
    employment = req.get("employment")
    values = {
        "CANDIDATE_HEADLINE": data.get("headline"),
        "CANDIDATE_NOTABLE": data.get("notable"),
        "CANDIDATE_YEARS_EXPERIENCE": data.get("years_experience"),
        "CANDIDATE_WORK_TYPE": req.get("work_type"),
        "CANDIDATE_ELIGIBILITY": req.get("eligibility"),
        "CANDIDATE_EMPLOYMENT": ",".join(employment)
        if isinstance(employment, list)
        else employment,
        "CANDIDATE_COMP_FLOOR_CAD": req.get("comp_floor_cad"),
    }
    have = {
        r.config_key
        for r in session.scalars(select(UserConfigItem).where(UserConfigItem.uid == uid))
    }
    for key, value in values.items():
        if key in have or value in (None, ""):
            continue
        session.add(UserConfigItem(uid=uid, config_key=key, value=str(value)))


def _import_config(session: Session, uid: str) -> None:
    """Seed the user's config values from env/settings (only where unset)."""
    have = {
        r.config_key
        for r in session.scalars(select(UserConfigItem).where(UserConfigItem.uid == uid))
    }
    for item in BUILTIN_CONFIG_ITEMS:
        key = item["key"]
        if key in have:
            continue
        value = _env_or_settings(key)
        if value:
            session.add(UserConfigItem(uid=uid, config_key=key, value=value))


# ── import helpers ────────────────────────────────────────────────────────────


def _find_or_create_prefilter(session, uid, category, value) -> PrefilterRule:
    rule = session.scalar(
        select(PrefilterRule).where(
            PrefilterRule.category == category,
            PrefilterRule.value == value,
            (PrefilterRule.owner_uid.is_(None)) | (PrefilterRule.owner_uid == uid),
        )
    )
    if rule is None:
        rule = PrefilterRule(category=category, value=value, owner_uid=uid)
        session.add(rule)
        session.flush()
    return rule


def _find_or_create_block(session, uid, block: dict[str, Any]) -> ScoringModifierBlock:
    name = block.get("name", "")
    found = session.scalar(
        select(ScoringModifierBlock).where(
            ScoringModifierBlock.name == name,
            (ScoringModifierBlock.owner_uid.is_(None)) | (ScoringModifierBlock.owner_uid == uid),
        )
    )
    if found is None:
        found = ScoringModifierBlock(
            name=name,
            modifier=int(block.get("modifier", 0)),
            examples=json.dumps(block.get("examples", []) or []),
            owner_uid=uid,
        )
        session.add(found)
        session.flush()
    return found


def _find_or_create_target_role(session, uid, kind, value) -> TargetRoleItem:
    item = session.scalar(
        select(TargetRoleItem).where(
            TargetRoleItem.kind == kind,
            TargetRoleItem.value == value,
            (TargetRoleItem.owner_uid.is_(None)) | (TargetRoleItem.owner_uid == uid),
        )
    )
    if item is None:
        item = TargetRoleItem(kind=kind, value=value, owner_uid=uid)
        session.add(item)
        session.flush()
    return item


def _apply_selection(session, uid, join_model, join_fk, wanted_ids: set[int]) -> None:
    """Make the user's selection exactly ``wanted_ids``: enable those, add missing,
    disable any currently-enabled join rows not wanted."""
    rows = {
        getattr(r, join_fk): r
        for r in session.scalars(select(join_model).where(join_model.uid == uid))
    }
    for cid in wanted_ids:
        row = rows.get(cid)
        if row is None:
            session.add(join_model(uid=uid, enabled=True, **{join_fk: cid}))
        else:
            row.enabled = True
    for cid, row in rows.items():
        if cid not in wanted_ids:
            row.enabled = False


# ── target-roles.md parsing (for one-time import) ─────────────────────────────

_TITLES_HEADING = "Target Role Titles"
_KEYWORDS_HEADING = "Title Keywords"
_DOMAINS_HEADING = "Domains of Interest"


def _parse_target_roles_md(text: str) -> dict[str, list[str]]:
    """Best-effort parse of a target-roles.md into {title, keyword, domain} lists."""
    sections = _split_md_sections(text)
    return {
        "title": _bullet_items(sections.get(_TITLES_HEADING, "")),
        "keyword": _keyword_items(sections.get(_KEYWORDS_HEADING, "")),
        "domain": _bullet_items(sections.get(_DOMAINS_HEADING, "")),
    }


def _split_md_sections(text: str) -> dict[str, str]:
    """Map each '## Heading' to the body text until the next heading."""
    sections: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*?)\s*$", line)
        if m:
            if current is not None:
                sections[current] = "\n".join(buf)
            # Normalize by matching on the known heading substrings.
            heading = m.group(1)
            current = next(
                (h for h in (_TITLES_HEADING, _KEYWORDS_HEADING, _DOMAINS_HEADING) if h in heading),
                heading,
            )
            buf = []
        elif current is not None:
            buf.append(line)
    if current is not None:
        sections[current] = "\n".join(buf)
    return sections


def _bullet_items(body: str) -> list[str]:
    items = []
    for line in body.splitlines():
        m = re.match(r"^\s*-\s+(.*\S)\s*$", line)
        if m:
            items.append(m.group(1).strip())
    return items


def _keyword_items(body: str) -> list[str]:
    """Keywords live in a fenced code block as comma-separated terms across lines."""
    inside = False
    collected: list[str] = []
    for line in body.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
            continue
        if inside:
            collected.append(line)
    blob = " ".join(collected)
    return [term.strip() for term in blob.split(",") if term.strip()]
