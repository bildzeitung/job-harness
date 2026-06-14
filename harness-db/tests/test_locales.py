"""Tests for harness_db.locales: locale catalog, user locale, and label resolution."""

from __future__ import annotations

import pytest

from harness_db import locales
from harness_db.config import DEFAULT_UID
from harness_db.seed import BUILTIN_CONFIG_ITEMS, DEFAULT_LOCALE, ensure_schema_and_seed


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """Point the resolver at a fresh, seeded tmp DB with no inherited config."""
    locales._engine_for.cache_clear()
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "postings.db"
    monkeypatch.setenv("HARNESS_DB", str(db))
    ensure_schema_and_seed(import_existing=False)
    return db


def test_default_locale_seeded():
    codes = {loc.code for loc in locales.list_locales()}
    assert DEFAULT_LOCALE in codes


def test_get_labels_match_builtin_catalog():
    labels = locales.get_labels(DEFAULT_LOCALE)
    for item in BUILTIN_CONFIG_ITEMS:
        label, help_text = labels[item["key"]]
        assert label == item["name"]
        assert help_text == item["description"]


def test_unknown_locale_falls_back_to_default():
    fr = locales.get_labels("fr-FR")
    en = locales.get_labels(DEFAULT_LOCALE)
    assert fr == en  # no fr-FR rows → every key falls back to en-US


def test_get_label_single_key():
    label, help_text = locales.get_label("RESUME_FILE", DEFAULT_LOCALE)
    assert label == "Resume file"
    assert "RenderCV" in (help_text or "")


def test_user_locale_defaults_to_en_us():
    assert locales.get_user_locale(DEFAULT_UID) == DEFAULT_LOCALE


def test_set_user_locale_round_trips():
    locales.set_user_locale(DEFAULT_LOCALE, DEFAULT_UID)
    assert locales.get_user_locale(DEFAULT_UID) == DEFAULT_LOCALE


def test_set_unknown_locale_raises():
    with pytest.raises(ValueError):
        locales.set_user_locale("xx-XX", DEFAULT_UID)


def test_label_falls_back_to_catalog_name_when_no_label_row():
    """A config key without a label row resolves to its catalog name."""
    from sqlalchemy.orm import Session

    from harness_db.models import ConfigItem, make_engine

    engine = make_engine(locales.get_db_path())
    with Session(engine) as s:
        s.add(ConfigItem(key="EXTRA_KEY", name="Extra", description="An extra key."))
        s.commit()
    label, help_text = locales.get_label("EXTRA_KEY", DEFAULT_LOCALE)
    assert label == "Extra"
    assert help_text == "An extra key."
