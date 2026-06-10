"""Tests for harness_db.companies — the per-platform company upsert (spec 14 A2)."""

from __future__ import annotations

import json

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from harness_db import cli, companies
from harness_db.models import Base, Company, make_engine

runner = CliRunner()


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    return eng


def _company(engine, name) -> Company | None:
    with Session(engine) as session:
        return session.get(Company, name)


def test_new_company_insert_sets_flags_and_note(engine):
    result = companies.record_seen(
        engine,
        [{"company": "Acme", "platform": "greenhouse"}],
        batch_date="2026-06-05",
    )
    assert result == {"companies": 1, "inserted": 1}
    c = _company(engine, "Acme")
    assert c.remote_confirmed is True
    assert c.canada_confirmed is True
    assert c.notes == "Hiring on Greenhouse (see posting URLs)"
    assert c.last_seen_date == "2026-06-05"


def test_note_uses_each_postings_own_ats_display(engine):
    companies.record_seen(
        engine,
        [{"company": "L", "platform": "lever"}, {"company": "A", "platform": "ashby"}],
        batch_date="2026-06-05",
    )
    assert _company(engine, "L").notes == "Hiring on Lever (see posting URLs)"
    assert _company(engine, "A").notes == "Hiring on Ashby (see posting URLs)"


def test_flags_ratchet_up_never_down(engine):
    # Greenhouse confirms both flags; a later linkedin posting (no flags) and an
    # indeed posting must not lower remote/canada.
    companies.record_seen(engine, [{"company": "Acme", "platform": "greenhouse"}], "2026-06-01")
    companies.record_seen(engine, [{"company": "Acme", "platform": "linkedin"}], "2026-06-02")
    companies.record_seen(engine, [{"company": "Acme", "platform": "indeed"}], "2026-06-03")
    c = _company(engine, "Acme")
    assert c.remote_confirmed is True
    assert c.canada_confirmed is True
    assert c.last_seen_date == "2026-06-03"  # advanced


def test_indeed_ratchets_canada_only(engine):
    companies.record_seen(engine, [{"company": "Acme", "platform": "indeed"}], "2026-06-01")
    c = _company(engine, "Acme")
    assert c.canada_confirmed is True
    assert c.remote_confirmed is None  # untouched
    assert c.notes is None


def test_last_seen_does_not_regress(engine):
    companies.record_seen(engine, [{"company": "Acme", "platform": "linkedin"}], "2026-06-05")
    companies.record_seen(engine, [{"company": "Acme", "platform": "linkedin"}], "2026-06-01")
    assert _company(engine, "Acme").last_seen_date == "2026-06-05"


def test_notes_fill_if_empty_does_not_overwrite(engine):
    with Session(engine) as session:
        session.add(Company(name="Acme", notes="hand-written intel"))
        session.commit()
    companies.record_seen(engine, [{"company": "Acme", "platform": "greenhouse"}], "2026-06-05")
    assert _company(engine, "Acme").notes == "hand-written intel"


def test_research_overwrites_notes_and_sets_researched_date(engine):
    with Session(engine) as session:
        session.add(Company(name="Acme", notes="stale note"))
        session.commit()
    companies.record_seen(
        engine,
        [{"company": "Acme", "platform": "research", "company_notes": "Series B, hiring fast"}],
        "2026-06-05",
    )
    c = _company(engine, "Acme")
    assert c.notes == "Series B, hiring fast"
    assert c.researched_date == "2026-06-05"
    assert c.remote_confirmed is True
    assert c.canada_confirmed is True


def test_research_without_notes_leaves_existing(engine):
    with Session(engine) as session:
        session.add(Company(name="Acme", notes="keep me"))
        session.commit()
    companies.record_seen(engine, [{"company": "Acme", "platform": "research"}], "2026-06-05")
    assert _company(engine, "Acme").notes == "keep me"


def test_apostrophe_in_company_name(engine):
    companies.record_seen(engine, [{"company": "O'Brien & Co", "platform": "indeed"}], "2026-06-05")
    assert _company(engine, "O'Brien & Co").canada_confirmed is True


def test_blank_company_names_skipped(engine):
    result = companies.record_seen(
        engine,
        [
            {"company": "", "platform": "indeed"},
            {"platform": "indeed"},
            {"company": "Real", "platform": "indeed"},
        ],
        "2026-06-05",
    )
    assert result == {"companies": 1, "inserted": 1}


def test_default_platform_used_when_posting_lacks_one(engine):
    companies.record_seen(engine, [{"company": "Acme"}], "2026-06-05", default_platform="adzuna")
    assert _company(engine, "Acme").canada_confirmed is True


def test_unknown_platform_raises(engine):
    with pytest.raises(ValueError, match="Unknown platform 'monster'"):
        companies.record_seen(engine, [{"company": "Acme", "platform": "monster"}], "2026-06-05")


def test_policy_covers_every_consolidator_platform():
    """Sync guard: every platform consolidator merges must have a flag policy."""
    from consolidate_module.consolidator import PLATFORMS

    missing = set(PLATFORMS) - set(companies.PLATFORM_POLICY)
    assert not missing, f"platforms without a company policy: {sorted(missing)}"


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_seen_reads_multiple_files(tmp_path):
    db = tmp_path / "postings.db"
    Base.metadata.create_all(make_engine(db))  # create the DB file + tables
    f1 = tmp_path / "greenhouse-2026-06-05.json"
    f1.write_text(
        json.dumps(
            {
                "platform": "greenhouse",
                "postings": [{"company": "GH Co", "platform": "greenhouse"}],
            }
        )
    )
    f2 = tmp_path / "lever-2026-06-05.json"  # bare array form
    f2.write_text(json.dumps([{"company": "Lever Co", "platform": "lever"}]))

    result = runner.invoke(
        cli.app,
        ["companies", "seen", "--db", str(db), "--date", "2026-06-05", str(f1), str(f2)],
    )
    assert result.exit_code == 0, result.stdout
    assert "2 companies (2 new)" in result.stdout
    engine = make_engine(db)
    with Session(engine) as session:
        assert session.get(Company, "GH Co").notes == "Hiring on Greenhouse (see posting URLs)"
        assert session.get(Company, "Lever Co").notes == "Hiring on Lever (see posting URLs)"


def test_cli_seen_unknown_platform_errors(tmp_path):
    db = tmp_path / "postings.db"
    Base.metadata.create_all(make_engine(db))
    f = tmp_path / "x-2026-06-05.json"
    f.write_text(json.dumps([{"company": "Acme", "platform": "monster"}]))
    result = runner.invoke(cli.app, ["companies", "seen", "--db", str(db), str(f)])
    assert result.exit_code == 1  # error message goes to stderr (Typer err=True)
