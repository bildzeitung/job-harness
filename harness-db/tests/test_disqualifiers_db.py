"""Tests for the DB-backed disqualifiers (loaders + CRUD)."""

from __future__ import annotations

import pytest

from harness_db import disqualifiers
from harness_db.config import DEFAULT_UID


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "postings.db"))
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    disqualifiers._engine_for.cache_clear()


def test_db_load_has_builtin_prefilter_and_modifiers():
    # Touch CRUD once to seed the DB.
    rules = disqualifiers.list_prefilter_rules(DEFAULT_UID)
    assert rules
    cfg = disqualifiers.load_disqualifiers(DEFAULT_UID)
    assert any(cfg["prefilter"].values())
    assert cfg["scoring_modifiers"]
    assert all({"name", "modifier", "examples"} <= set(b) for b in cfg["scoring_modifiers"])


def test_disabling_a_rule_drops_it_from_prefilter():
    rules = disqualifiers.list_prefilter_rules(DEFAULT_UID)
    target = next(r for r in rules if r.category == "title_terms")
    disqualifiers.set_prefilter_enabled(target.id, False, DEFAULT_UID)
    pf = disqualifiers.load_prefilter(DEFAULT_UID)
    assert target.value not in pf.get("title_terms", [])


def test_add_and_delete_custom_prefilter_rule():
    rid = disqualifiers.add_prefilter_rule("title_terms", "widgetmaster", DEFAULT_UID)
    pf = disqualifiers.load_prefilter(DEFAULT_UID)
    assert "widgetmaster" in pf["title_terms"]
    disqualifiers.delete_prefilter_rule(rid, DEFAULT_UID)
    pf = disqualifiers.load_prefilter(DEFAULT_UID)
    assert "widgetmaster" not in pf.get("title_terms", [])


def test_cannot_delete_builtin_rule():
    builtin = next(r for r in disqualifiers.list_prefilter_rules(DEFAULT_UID) if not r.custom)
    with pytest.raises(ValueError):
        disqualifiers.delete_prefilter_rule(builtin.id, DEFAULT_UID)


def test_scoring_block_add_and_load():
    bid = disqualifiers.add_scoring_block("No widgets", -15, ["widget"], DEFAULT_UID)
    cfg = disqualifiers.load_disqualifiers(DEFAULT_UID)
    names = {b["name"]: b for b in cfg["scoring_modifiers"]}
    assert "No widgets" in names
    assert names["No widgets"]["modifier"] == -15
    disqualifiers.set_scoring_enabled(bid, False, DEFAULT_UID)
    cfg = disqualifiers.load_disqualifiers(DEFAULT_UID)
    assert "No widgets" not in {b["name"] for b in cfg["scoring_modifiers"]}


def test_new_user_is_provisioned_on_read_path():
    """A freshly created user must see built-in disqualifiers via the read path,
    not only after opening a Settings sub-tab."""
    from harness_db import users
    from harness_db.seed import ensure_schema_and_seed

    engine = ensure_schema_and_seed(import_existing=False)
    users.create_user(engine, "newbie")
    pf = disqualifiers.load_prefilter("newbie")
    assert any(pf.values())  # built-in prefilter rules enabled for the new user


def test_db_takes_priority_over_file(monkeypatch, tmp_path):
    # Seed DB and add a custom rule, then write a conflicting yaml file.
    disqualifiers.add_prefilter_rule("title_terms", "fromdb", DEFAULT_UID)
    data_root = tmp_path / "data"
    data_root.mkdir()
    monkeypatch.setenv("JOB_DATA_ROOT", str(data_root))
    (data_root / "disqualifiers.yaml").write_text("prefilter:\n  title_terms:\n    - fromfile\n")
    pf = disqualifiers.load_prefilter(DEFAULT_UID)
    assert "fromdb" in pf["title_terms"]
    assert "fromfile" not in pf.get("title_terms", [])
