"""Tests for harness_db.sources_store."""

from __future__ import annotations

import pytest

from harness_db import config_store, sources_store
from harness_db.config import DEFAULT_UID


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "postings.db"))
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    sources_store._engine.cache_clear()
    config_store._engine_for.cache_clear()


def test_list_sources_defaults_all_enabled():
    sources = sources_store.list_sources(DEFAULT_UID)
    assert len(sources) == 7
    assert all(s.enabled for s in sources)


def test_enabled_source_ids_reflects_toggle():
    sources_store.set_enabled("linkedin", False, DEFAULT_UID)
    ids = sources_store.enabled_source_ids(DEFAULT_UID)
    assert "linkedin" not in ids
    assert "adzuna" in ids


def test_set_enabled_round_trip():
    sources_store.set_enabled("linkedin", False, DEFAULT_UID)
    sources_store.set_enabled("linkedin", True, DEFAULT_UID)
    assert "linkedin" in sources_store.enabled_source_ids(DEFAULT_UID)
