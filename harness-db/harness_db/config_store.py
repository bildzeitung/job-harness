"""Per-user configuration values, read from the DB with an env-var fallback.

This is the single resolver every module/front-end uses for config items
(``RESUME_FILE``, ``ADZUNA_APP_ID``, ``ADZUNA_API_KEY``, ``JOB_DATA_ROOT``).

Resolution order for ``get_config(key, uid)``:

1. the active user's stored value in ``user_config_items``;
2. the process env var / ``settings.local.json`` fallback (so an un-migrated
   single-user install keeps working);
3. otherwise raise ``KeyError``.

The DB lookup is defensive: if the DB file or schema is absent, it silently
falls through to the env fallback rather than failing the pipeline.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import DEFAULT_UID, _env_or_settings, get_active_uid, get_db_path
from harness_db.models import ConfigItem, UserConfigItem, make_engine

__all__ = [
    "get_config",
    "get_config_optional",
    "set_config",
    "list_config",
    "iter_config_items",
]


@lru_cache(maxsize=8)
def _engine_for(db_path_str: str) -> Engine:
    return make_engine(db_path_str if db_path_str else get_db_path())


def _engine() -> Engine | None:
    """Engine for the resolved DB path, or None if the DB path/file is absent."""
    try:
        db_path = get_db_path()
    except RuntimeError:
        # No HARNESS_DB / JOB_DATA_ROOT configured — env fallback is the only path.
        return None
    if not db_path.exists():
        return None
    return _engine_for(str(db_path))


def _resolve_uid(uid: str | None) -> str:
    if uid:
        return uid
    try:
        return get_active_uid()
    except RuntimeError:
        return DEFAULT_UID


def _db_value(key: str, uid: str) -> str | None:
    engine = _engine()
    if engine is None:
        return None
    try:
        with Session(engine) as session:
            row = session.scalar(
                select(UserConfigItem).where(
                    UserConfigItem.uid == uid, UserConfigItem.config_key == key
                )
            )
            return row.value if row and row.value else None
    except Exception:
        # Missing schema / locked DB / etc. — defer to the env fallback.
        return None


def get_config_optional(key: str, uid: str | None = None) -> str | None:
    """Resolve ``key`` for the user; None if neither DB nor env provide it."""
    uid = _resolve_uid(uid)
    return _db_value(key, uid) or _env_or_settings(key)


def get_config(key: str, uid: str | None = None) -> str:
    """Resolve ``key`` for the user; raise ``KeyError`` if unset everywhere."""
    value = get_config_optional(key, uid)
    if value is None:
        raise KeyError(
            f"Config {key!r} is not set for the active user and no env fallback is present."
        )
    return value


def set_config(key: str, value: str, uid: str | None = None) -> None:
    """Upsert a config value for the user. Ensures the user + catalog rows exist."""
    from harness_db.seed import ensure_schema_and_seed

    uid = _resolve_uid(uid)
    engine = ensure_schema_and_seed(import_existing=False)
    with Session(engine) as session:
        # Make sure the catalog key exists so it shows up in listings.
        if session.get(ConfigItem, key) is None:
            session.add(ConfigItem(key=key, name=key, description=None))
        row = session.scalar(
            select(UserConfigItem).where(
                UserConfigItem.uid == uid, UserConfigItem.config_key == key
            )
        )
        if row is None:
            session.add(UserConfigItem(uid=uid, config_key=key, value=value))
        else:
            row.value = value
        session.commit()


def list_config(uid: str | None = None) -> dict[str, str | None]:
    """Map every catalog config key to the user's resolved value (DB → env)."""
    uid = _resolve_uid(uid)
    return {item.key: get_config_optional(item.key, uid) for item in iter_config_items()}


def iter_config_items() -> list[ConfigItem]:
    """All known config-key catalog rows (empty if the DB is absent)."""
    engine = _engine()
    if engine is None:
        return []
    try:
        with Session(engine) as session:
            items = list(session.scalars(select(ConfigItem).order_by(ConfigItem.key)))
            for i in items:
                session.expunge(i)
            return items
    except Exception:
        return []
