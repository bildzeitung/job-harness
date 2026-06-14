"""Locale catalog and localized config-item labels (spec 15).

The Settings → Config keys carry language-neutral catalog rows (``config_items``);
their human-friendly label + help text live per-locale in ``config_item_labels``.
This module is the single resolver both front-ends use to turn a config key into
the string a given user should see.

Label resolution for ``get_labels(locale)`` is per-key and always succeeds:

1. the requested ``locale``'s label/help text;
2. the ``DEFAULT_LOCALE`` (en-US) label/help text;
3. the language-neutral ``ConfigItem.name`` / ``description``;
4. the raw key (label) with no help text.

DB access is defensive like :mod:`harness_db.config_store`: a missing DB/schema
falls back to the catalog name rather than failing the front-end.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.config import DEFAULT_UID, get_active_uid, get_db_path
from harness_db.models import ConfigItem, ConfigItemLabel, Locale, User, make_engine
from harness_db.seed import DEFAULT_LOCALE

__all__ = [
    "DEFAULT_LOCALE",
    "list_locales",
    "get_user_locale",
    "set_user_locale",
    "get_labels",
    "get_label",
]


@lru_cache(maxsize=8)
def _engine_for(db_path_str: str) -> Engine:
    return make_engine(db_path_str if db_path_str else get_db_path())


def _engine() -> Engine | None:
    """Engine for the resolved DB path, or None if the DB path/file is absent."""
    try:
        db_path = get_db_path()
    except RuntimeError:
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


def list_locales() -> list[Locale]:
    """All active locales in the catalog (empty if the DB is absent)."""
    engine = _engine()
    if engine is None:
        return []
    try:
        with Session(engine) as session:
            rows = list(session.scalars(select(Locale).where(Locale.active).order_by(Locale.code)))
            for r in rows:
                session.expunge(r)
            return rows
    except Exception:
        return []


def get_user_locale(uid: str | None = None) -> str:
    """The user's locale, defaulting to ``DEFAULT_LOCALE`` when unset/absent."""
    uid = _resolve_uid(uid)
    engine = _engine()
    if engine is None:
        return DEFAULT_LOCALE
    try:
        with Session(engine) as session:
            user = session.get(User, uid)
            return user.locale if user and user.locale else DEFAULT_LOCALE
    except Exception:
        return DEFAULT_LOCALE


def set_user_locale(code: str, uid: str | None = None) -> None:
    """Set the user's locale. Raises ``ValueError`` for an unknown locale code."""
    from harness_db.seed import ensure_schema_and_seed

    uid = _resolve_uid(uid)
    engine = ensure_schema_and_seed(import_existing=False)
    with Session(engine) as session:
        if session.get(Locale, code) is None:
            raise ValueError(f"Unknown locale {code!r}")
        from harness_db.users import _now

        user = session.get(User, uid)
        if user is None:
            user = User(uid=uid, active=True, created_at=_now())
            session.add(user)
        user.locale = code
        session.commit()


def get_labels(locale: str | None = None) -> dict[str, tuple[str, str | None]]:
    """Map every config key to its ``(label, help_text)`` for ``locale``.

    Resolution falls back per key: ``locale`` → ``DEFAULT_LOCALE`` → catalog
    name/description → the raw key. Always returns a label for every catalog key.
    """
    locale = locale or DEFAULT_LOCALE
    engine = _engine()
    if engine is None:
        return {}
    try:
        with Session(engine) as session:
            items = list(session.scalars(select(ConfigItem)))
            wanted = {locale, DEFAULT_LOCALE}
            labels = {
                (lbl.config_key, lbl.locale): lbl
                for lbl in session.scalars(
                    select(ConfigItemLabel).where(ConfigItemLabel.locale.in_(wanted))
                )
            }
            result: dict[str, tuple[str, str | None]] = {}
            for item in items:
                row = labels.get((item.key, locale)) or labels.get((item.key, DEFAULT_LOCALE))
                if row is not None:
                    result[item.key] = (row.label, row.help_text)
                else:
                    result[item.key] = (item.name or item.key, item.description)
            return result
    except Exception:
        return {}


def get_label(key: str, locale: str | None = None) -> tuple[str, str | None]:
    """The ``(label, help_text)`` for a single config key (see :func:`get_labels`)."""
    return get_labels(locale).get(key, (key, None))
