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
