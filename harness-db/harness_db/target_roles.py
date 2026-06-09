"""Target-role catalog and the shared ``target-roles.md`` generator.

The candidate's positive search inputs — target role titles, title keywords, and
domains of interest — are data-driven and per-user, stored in the harness DB.

:func:`render_target_roles_md` is the single library both the TUI and the web UI
call to produce the Markdown file the searchers read
(``$JOB_DATA_ROOT/target-roles.md``), so file generation lives in one place.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import get_active_uid, get_db_path, get_job_data_root
from harness_db.models import TargetRoleItem, UserTargetRole, make_engine
from harness_db.seed import ensure_schema_and_seed, ensure_user_defaults

__all__ = [
    "TargetRoleView",
    "KINDS",
    "render_target_roles_md",
    "write_target_roles_md",
    "list_target_roles",
    "enabled_values",
    "set_enabled",
    "add_target_role",
    "delete_target_role",
]

KINDS = ("title", "keyword", "domain")
_TARGET_ROLES_FILENAME = "target-roles.md"


@dataclass(frozen=True)
class TargetRoleView:
    id: int
    kind: str
    value: str
    enabled: bool
    custom: bool


@lru_cache(maxsize=8)
def _engine_for(db_path_str: str) -> Engine:
    return make_engine(db_path_str)


def _engine() -> Engine:
    # Reuse the cached engine for the DB path so repeated reads/edits don't
    # rebuild the connection pool each call; the seed is idempotent.
    return ensure_schema_and_seed(_engine_for(str(get_db_path())), import_existing=False)


def _enabled_by_kind(session: Session, uid: str) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {k: [] for k in KINDS}
    rows = session.execute(
        select(TargetRoleItem)
        .join(UserTargetRole, UserTargetRole.item_id == TargetRoleItem.id)
        .where(UserTargetRole.uid == uid, UserTargetRole.enabled.is_(True))
        .order_by(TargetRoleItem.id)
    ).scalars()
    for r in rows:
        grouped.setdefault(r.kind, []).append(r.value)
    return grouped


# ── the shared file generator ─────────────────────────────────────────────────


def render_target_roles_md(uid: str | None = None) -> str:
    """Render the target-roles Markdown for a user from their enabled selections."""
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        ensure_user_defaults(session, uid)
        session.commit()
        grouped = _enabled_by_kind(session, uid)
    return _format_md(grouped["title"], grouped["keyword"], grouped["domain"])


def write_target_roles_md(uid: str | None = None, path=None):
    """Generate and write ``target-roles.md`` (default: under ``$JOB_DATA_ROOT``).

    Returns the path written.
    """
    content = render_target_roles_md(uid)
    target = path or (get_job_data_root() / _TARGET_ROLES_FILENAME)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def _format_md(titles: list[str], keywords: list[str], domains: list[str]) -> str:
    title_lines = "\n".join(f"- {t}" for t in titles) or "- (none configured)"
    keyword_block = _wrap_keywords(keywords)
    domain_lines = "\n".join(f"- {d}" for d in domains) or "- (none configured)"
    return f"""# Target Job Roles

This is the canonical list of job types you are targeting. The `job-seeker`
pipeline reads it from the harness DB at runtime (`harness-db target-roles show`)
instead of using hardcoded lists.

**Rendered from the harness DB** — edit it from the TUI/web Settings → Target
Roles panel, not by hand (this rendering reflects the DB, which is the source
of truth).

Positive *targets* live here. Hard *exclusions* live in the disqualifiers config.

## Target Role Titles

{title_lines}

## Title Keywords (for search queries and filtering)

Any posting whose title contains one or more of these keywords qualifies by
seniority:

```
{keyword_block}
```

## Domains of Interest

{domain_lines}

## How to Use This

The pipeline renders this straight from the DB:

```bash
harness-db target-roles show
```

Use the **Title Keywords** section to drive search queries and filter results.
"""


def _wrap_keywords(keywords: list[str]) -> str:
    if not keywords:
        return "(none configured)"
    return textwrap.fill(", ".join(keywords), width=78)


# ── CRUD for the TUI / web / CLI ──────────────────────────────────────────────


def list_target_roles(uid: str | None = None) -> list[TargetRoleView]:
    """All target-role items visible to the user (built-ins + own), with enabled flag."""
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        ensure_user_defaults(session, uid)
        session.commit()
        enabled = {
            r.item_id: r.enabled
            for r in session.scalars(select(UserTargetRole).where(UserTargetRole.uid == uid))
        }
        items = session.scalars(
            select(TargetRoleItem)
            .where((TargetRoleItem.owner_uid.is_(None)) | (TargetRoleItem.owner_uid == uid))
            .order_by(TargetRoleItem.kind, TargetRoleItem.value)
        )
        return [
            TargetRoleView(
                id=i.id,
                kind=i.kind,
                value=i.value,
                enabled=enabled.get(i.id, False),
                custom=i.owner_uid == uid,
            )
            for i in items
        ]


def enabled_values(kind: str, uid: str | None = None) -> list[str]:
    """Enabled values for one kind (``title``/``keyword``/``domain``)."""
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        ensure_user_defaults(session, uid)
        session.commit()
        return _enabled_by_kind(session, uid).get(kind, [])


def set_enabled(item_id: int, enabled: bool, uid: str | None = None) -> None:
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        row = session.scalar(
            select(UserTargetRole).where(
                UserTargetRole.uid == uid, UserTargetRole.item_id == item_id
            )
        )
        if row is None:
            session.add(UserTargetRole(uid=uid, item_id=item_id, enabled=enabled))
        else:
            row.enabled = enabled
        session.commit()


def add_target_role(kind: str, value: str, uid: str | None = None) -> int:
    """Add a custom target-role item for the user (enabled). Returns the new id."""
    if kind not in KINDS:
        raise ValueError(f"Unknown target-role kind {kind!r}")
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        item = TargetRoleItem(kind=kind, value=value, owner_uid=uid)
        session.add(item)
        session.flush()
        session.add(UserTargetRole(uid=uid, item_id=item.id, enabled=True))
        session.commit()
        return item.id


def delete_target_role(item_id: int, uid: str | None = None) -> None:
    """Delete a custom item the user owns (built-ins can only be disabled)."""
    uid = uid or get_active_uid()
    with Session(_engine()) as session:
        item = session.get(TargetRoleItem, item_id)
        if item is None:
            return
        if item.owner_uid != uid:
            raise ValueError("Only custom items you own can be deleted; disable built-ins instead.")
        session.execute(
            UserTargetRole.__table__.delete().where(
                UserTargetRole.uid == uid, UserTargetRole.item_id == item_id
            )
        )
        session.delete(item)
        session.commit()
