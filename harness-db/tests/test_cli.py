"""Tests for the harness-db CLI: report --json and the candidate command."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from harness_db import cli
from harness_db.models import Base, Posting, make_engine

runner = CliRunner()


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "postings.db"
    engine = make_engine(path)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(
            Posting(
                url="https://job/1",
                title="Principal Engineer",
                company="Acme",
                platform="linkedin",
                status="scored",
                final_score=90,
                applicant_count=4,
            )
        )
        session.add(Posting(url="https://job/2", status="scored", final_score=60))
        session.commit()
    return path


def test_report_json_emits_structured_ranking(db_path):
    result = runner.invoke(
        cli.app,
        ["report", "--db", str(db_path), "--json", "--min-score", "75", "--top", "5"],
    )
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["scored_total"] == 2
    assert data["scored_below_min"] == 1
    assert [row["url"] for row in data["top"]] == ["https://job/1"]
    assert data["top"][0]["company"] == "Acme"


def test_report_text_is_default(db_path):
    result = runner.invoke(cli.app, ["report", "--db", str(db_path)])
    assert result.exit_code == 0
    out = result.stdout
    assert "By status" in out  # text renderer, not JSON
    assert not out.lstrip().startswith("{")


def test_candidate_prints_field(monkeypatch):
    monkeypatch.setattr(cli, "load_candidate_summary", lambda: {"name": "Jane Smith"})
    result = runner.invoke(cli.app, ["candidate"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Jane Smith"


def test_candidate_filename_safe_underscores_spaces(monkeypatch):
    monkeypatch.setattr(cli, "load_candidate_summary", lambda: {"name": "Jane Smith"})
    result = runner.invoke(cli.app, ["candidate", "--filename-safe"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "Jane_Smith"


def test_candidate_missing_field_errors(monkeypatch):
    monkeypatch.setattr(cli, "load_candidate_summary", lambda: {"name": "Jane Smith"})
    result = runner.invoke(cli.app, ["candidate", "--field", "nope"])
    assert result.exit_code != 0


@pytest.fixture
def prefilter_db_path(tmp_path):
    """Two 'new' postings (one disqualified by 'defi', one clean) and one 'scored'."""
    path = tmp_path / "postings.db"
    engine = make_engine(path)
    Base.metadata.create_all(engine)
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(
            Posting(
                url="https://job/defi",
                title="Senior Engineer",
                company="CryptoCo",
                status="new",
                description_summary="We build a DeFi protocol on Ethereum.",
            )
        )
        session.add(
            Posting(
                url="https://job/clean",
                title="Staff Engineer",
                company="Acme",
                status="new",
                description_summary="The architect defines and refines our APIs.",
            )
        )
        session.add(Posting(url="https://job/scored", title="Lead", status="scored"))
        session.commit()
    return path


def test_postings_json_filters_by_status(prefilter_db_path):
    result = runner.invoke(cli.app, ["postings", "--db", str(prefilter_db_path), "--status", "new"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert {r["url"] for r in rows} == {"https://job/defi", "https://job/clean"}
    # Default projection omits the large job_description_text field.
    assert "job_description_text" not in rows[0]
    assert "description_summary" in rows[0]


def test_postings_full_includes_job_description_text(prefilter_db_path):
    result = runner.invoke(cli.app, ["postings", "--db", str(prefilter_db_path), "--full"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert all("job_description_text" in r for r in rows)


def test_prefilter_lists_disqualified_word_bounded(prefilter_db_path, monkeypatch):
    # "defi" disqualifies the DeFi posting but not the one that merely "defines".
    monkeypatch.setattr(cli, "load_prefilter", lambda: {"description_phrases": ["defi"]})
    result = runner.invoke(cli.app, ["prefilter", "--db", str(prefilter_db_path), "--json"])
    assert result.exit_code == 0
    rows = json.loads(result.stdout)
    assert [r["url"] for r in rows] == ["https://job/defi"]


def test_prefilter_apply_marks_skipped(prefilter_db_path, monkeypatch):
    monkeypatch.setattr(cli, "load_prefilter", lambda: {"description_phrases": ["defi"]})
    result = runner.invoke(cli.app, ["prefilter", "--db", str(prefilter_db_path), "--apply"])
    assert result.exit_code == 0

    from sqlalchemy.orm import Session

    with Session(make_engine(prefilter_db_path)) as session:
        assert session.get(Posting, "https://job/defi").status == "skipped"
        assert session.get(Posting, "https://job/clean").status == "new"
