"""Tests for harness_db.config_store: DB value, env fallback, and CRUD."""

from __future__ import annotations

import pytest

from harness_db import config_store
from harness_db.config import DEFAULT_UID


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point the resolver at a tmp DB and clear inherited config.

    chdir into tmp so no repo .git / settings.local.json is discovered, and clear
    the env vars so neither fallback leaks real config into the assertions.
    """
    config_store._engine_for.cache_clear()
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "postings.db"
    monkeypatch.setenv("HARNESS_DB", str(db))
    for key in ("ADZUNA_APP_ID", "ADZUNA_API_KEY", "RESUME_FILE"):
        monkeypatch.delenv(key, raising=False)
    return db


def test_env_fallback_when_db_absent(monkeypatch):
    monkeypatch.setenv("RESUME_FILE", "/from/env.yaml")
    assert config_store.get_config("RESUME_FILE") == "/from/env.yaml"


def test_missing_everywhere_raises():
    with pytest.raises(KeyError):
        config_store.get_config("RESUME_FILE")


def test_optional_returns_none_when_unset():
    assert config_store.get_config_optional("RESUME_FILE") is None


def test_set_then_get_reads_from_db():
    config_store.set_config("RESUME_FILE", "/db/value.yaml")
    assert config_store.get_config("RESUME_FILE") == "/db/value.yaml"


def test_db_value_takes_priority_over_env(monkeypatch):
    config_store.set_config("ADZUNA_APP_ID", "db_id")
    monkeypatch.setenv("ADZUNA_APP_ID", "env_id")
    assert config_store.get_config("ADZUNA_APP_ID") == "db_id"


def test_list_config_includes_catalog_keys():
    config_store.set_config("RESUME_FILE", "/x.yaml", uid=DEFAULT_UID)
    cfg = config_store.list_config(DEFAULT_UID)
    assert cfg["RESUME_FILE"] == "/x.yaml"
    # Other seeded catalog keys present with None values.
    assert "ADZUNA_API_KEY" in cfg
