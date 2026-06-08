"""User identity CRUD for the multi-user harness (spec 12, phase 1).

A user is just a profile identifier plus an active flag. Configuration, source
selection, disqualifiers, and target roles all hang off the uid via their own
per-user join tables (see :mod:`harness_db.models`). This phase does not scope
postings/companies by user.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from harness_db.models import User

__all__ = [
    "create_user",
    "ensure_user",
    "get_user",
    "list_users",
    "set_active",
    "user_exists",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_user(engine: Engine, uid: str, active: bool = True) -> User:
    """Create a new user. Raises ValueError if the uid already exists."""
    with Session(engine) as session:
        if session.get(User, uid) is not None:
            raise ValueError(f"User {uid!r} already exists")
        user = User(uid=uid, active=active, created_at=_now())
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
    return user


def ensure_user(engine: Engine, uid: str, active: bool = True) -> User:
    """Return the user, creating it if absent (idempotent)."""
    with Session(engine) as session:
        user = session.get(User, uid)
        if user is None:
            user = User(uid=uid, active=active, created_at=_now())
            session.add(user)
            session.commit()
            session.refresh(user)
        session.expunge(user)
    return user


def get_user(engine: Engine, uid: str) -> User | None:
    with Session(engine) as session:
        user = session.get(User, uid)
        if user is not None:
            session.expunge(user)
        return user


def user_exists(engine: Engine, uid: str) -> bool:
    with Session(engine) as session:
        return session.get(User, uid) is not None


def list_users(engine: Engine) -> list[User]:
    with Session(engine) as session:
        users = list(session.scalars(select(User).order_by(User.uid)))
        for u in users:
            session.expunge(u)
        return users


def set_active(engine: Engine, uid: str, active: bool) -> None:
    """Set a user's active flag. Raises ValueError if the user is unknown."""
    with Session(engine) as session:
        user = session.get(User, uid)
        if user is None:
            raise ValueError(f"Unknown user {uid!r}")
        user.active = active
        session.commit()
