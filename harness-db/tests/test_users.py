"""Tests for harness_db.users CRUD."""

from __future__ import annotations

import pytest

from harness_db import users
from harness_db.models import Base, make_engine


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    return eng


def test_create_and_get_user(engine):
    users.create_user(engine, "alice")
    u = users.get_user(engine, "alice")
    assert u is not None
    assert u.uid == "alice"
    assert u.active is True
    assert u.created_at  # timestamp set


def test_create_duplicate_raises(engine):
    users.create_user(engine, "bob")
    with pytest.raises(ValueError):
        users.create_user(engine, "bob")


def test_ensure_user_is_idempotent(engine):
    users.ensure_user(engine, "carol")
    users.ensure_user(engine, "carol")
    assert [u.uid for u in users.list_users(engine)] == ["carol"]


def test_set_active_toggles_flag(engine):
    users.create_user(engine, "dave")
    users.set_active(engine, "dave", False)
    assert users.get_user(engine, "dave").active is False


def test_set_active_unknown_raises(engine):
    with pytest.raises(ValueError):
        users.set_active(engine, "ghost", True)


def test_list_users_sorted(engine):
    users.create_user(engine, "zed")
    users.create_user(engine, "amy")
    assert [u.uid for u in users.list_users(engine)] == ["amy", "zed"]
