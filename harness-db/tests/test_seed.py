"""Tests for harness_db.seed: catalog seeding, default selection, and file import."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_db.config import DEFAULT_UID
from harness_db.models import (
    ConfigItem,
    PrefilterRule,
    ScoringModifierBlock,
    Source,
    TargetRoleItem,
    User,
    UserConfigItem,
    UserPrefilterRule,
    UserSource,
    UserTargetRole,
    make_engine,
)
from harness_db.seed import BUILTIN_CONFIG_ITEMS, BUILTIN_SOURCES, ensure_schema_and_seed


@pytest.fixture
def engine(tmp_path):
    return make_engine(tmp_path / "test.db")


def test_seed_creates_catalogs_and_default_user(engine):
    ensure_schema_and_seed(engine, import_existing=False)
    with Session(engine) as s:
        assert s.get(User, DEFAULT_UID) is not None
        assert set(s.scalars(select(Source.source_id))) == {x["source_id"] for x in BUILTIN_SOURCES}
        assert s.scalar(select(PrefilterRule.id).limit(1)) is not None
        assert s.scalar(select(ScoringModifierBlock.id).limit(1)) is not None
        assert s.scalar(select(TargetRoleItem.id).limit(1)) is not None
        config_keys = set(s.scalars(select(ConfigItem.key)))
        assert {x["key"] for x in BUILTIN_CONFIG_ITEMS} <= config_keys
        assert "JOB_TOP_N" in config_keys


def test_default_user_has_all_builtins_enabled(engine):
    ensure_schema_and_seed(engine, import_existing=False)
    with Session(engine) as s:
        n_sources = len(list(s.scalars(select(Source.source_id))))
        n_user_sources = len(
            list(s.scalars(select(UserSource).where(UserSource.uid == DEFAULT_UID)))
        )
        assert n_user_sources == n_sources
        assert all(
            r.enabled for r in s.scalars(select(UserSource).where(UserSource.uid == DEFAULT_UID))
        )


def test_seed_is_idempotent(engine):
    ensure_schema_and_seed(engine, import_existing=False)
    with Session(engine) as s:
        before = len(list(s.scalars(select(PrefilterRule.id))))
    ensure_schema_and_seed(engine, import_existing=False)
    with Session(engine) as s:
        after = len(list(s.scalars(select(PrefilterRule.id))))
    assert before == after


def test_import_existing_applies_files(engine, tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    (data_root / "jobs").mkdir(parents=True)
    monkeypatch.setenv("JOB_DATA_ROOT", str(data_root))
    monkeypatch.setenv("RESUME_FILE", "/path/to/cv.yaml")
    monkeypatch.setenv("JOB_TOP_N", "7")

    (data_root / "jobs" / "sources-config.json").write_text(
        json.dumps({"enabled": ["adzuna", "greenhouse"]})
    )
    (data_root / "disqualifiers.yaml").write_text(
        "prefilter:\n"
        "  title_terms:\n"
        "    - widget\n"
        "scoring_modifiers:\n"
        "  - name: Custom block\n"
        "    modifier: -10\n"
        "    examples: [foo]\n"
    )
    (data_root / "target-roles.md").write_text(
        "## Target Role Titles\n\n- Galaxy Engineer\n\n"
        "## Title Keywords\n\n```\nGalaxy, Nebula\n```\n\n"
        "## Domains of Interest\n\n- Astro\n"
    )

    ensure_schema_and_seed(engine, import_existing=True)

    with Session(engine) as s:
        enabled_sources = {
            r.source_id
            for r in s.scalars(select(UserSource).where(UserSource.uid == DEFAULT_UID))
            if r.enabled
        }
        assert enabled_sources == {"adzuna", "greenhouse"}

        # Custom prefilter rule imported and enabled.
        widget = s.scalar(select(PrefilterRule).where(PrefilterRule.value == "widget"))
        assert widget is not None and widget.owner_uid == DEFAULT_UID
        enabled_rule_ids = {
            r.rule_id
            for r in s.scalars(
                select(UserPrefilterRule).where(UserPrefilterRule.uid == DEFAULT_UID)
            )
            if r.enabled
        }
        assert widget.id in enabled_rule_ids

        # Target roles parsed across all three sections.
        values = {i.value for i in s.scalars(select(TargetRoleItem))}
        assert {"Galaxy Engineer", "Galaxy", "Nebula", "Astro"} <= values
        enabled_item_ids = {
            r.item_id
            for r in s.scalars(select(UserTargetRole).where(UserTargetRole.uid == DEFAULT_UID))
            if r.enabled
        }
        galaxy = s.scalar(select(TargetRoleItem).where(TargetRoleItem.value == "Galaxy Engineer"))
        assert galaxy.id in enabled_item_ids

        # Config value imported from env.
        rf = s.scalar(
            select(UserConfigItem).where(
                UserConfigItem.uid == DEFAULT_UID, UserConfigItem.config_key == "RESUME_FILE"
            )
        )
        assert rf is not None and rf.value == "/path/to/cv.yaml"
        top_n = s.scalar(
            select(UserConfigItem).where(
                UserConfigItem.uid == DEFAULT_UID, UserConfigItem.config_key == "JOB_TOP_N"
            )
        )
        assert top_n is not None and top_n.value == "7"


def test_import_runs_once_not_on_rerun(engine, tmp_path, monkeypatch):
    data_root = tmp_path / "data"
    (data_root / "jobs").mkdir(parents=True)
    monkeypatch.setenv("JOB_DATA_ROOT", str(data_root))
    (data_root / "jobs" / "sources-config.json").write_text(json.dumps({"enabled": ["adzuna"]}))

    ensure_schema_and_seed(engine, import_existing=True)
    # User disables adzuna via the UI afterwards.
    with Session(engine) as s:
        row = s.scalar(
            select(UserSource).where(
                UserSource.uid == DEFAULT_UID, UserSource.source_id == "adzuna"
            )
        )
        row.enabled = False
        s.commit()

    # Re-running seed must NOT re-import and re-enable adzuna.
    ensure_schema_and_seed(engine, import_existing=True)
    with Session(engine) as s:
        row = s.scalar(
            select(UserSource).where(
                UserSource.uid == DEFAULT_UID, UserSource.source_id == "adzuna"
            )
        )
        assert row.enabled is False
