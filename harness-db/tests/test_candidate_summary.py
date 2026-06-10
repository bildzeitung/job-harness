"""Tests for harness_db.candidate_summary — deterministic assembly (spec 14 A4)."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from harness_db import cli
from harness_db.candidate_summary import build_summary, write_summary
from harness_db.config_store import get_config_optional, set_config
from harness_db.seed import ensure_schema_and_seed

runner = CliRunner()

_RESUME_YAML = """\
cv:
  name: Test User
  location: Testville, ON, Canada
  sections:
    skills:
      - label: Languages
        details: Python, Java, Python
      - label: Cloud
        details: AWS, Azure, Python
"""


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Isolated JOB_DATA_ROOT (DB at <root>/jobs/postings.db) + a resume fixture."""
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("HARNESS_DB", raising=False)
    (tmp_path / "jobs").mkdir()  # DB lives at <root>/jobs/postings.db
    resume = tmp_path / "cv.yaml"
    resume.write_text(_RESUME_YAML)
    return tmp_path, resume


def test_assembly_from_resume_target_roles_and_config(env):
    tmp_path, resume = env
    set_config("RESUME_FILE", str(resume))  # also creates the default user (no import)
    set_config("CANDIDATE_HEADLINE", "Principal Engineer — Cloud")
    set_config("CANDIDATE_NOTABLE", "13 years at Oracle")
    set_config("CANDIDATE_YEARS_EXPERIENCE", "20")

    summary = build_summary()
    assert summary["name"] == "Test User"
    assert summary["location"] == "Testville, ON, Canada"
    # Comma-split skills details, order-preserving, deduped across entries.
    assert summary["stack"] == ["Python", "Java", "AWS", "Azure"]
    assert summary["headline"] == "Principal Engineer — Cloud"
    assert summary["notable"] == "13 years at Oracle"
    assert summary["years_experience"] == 20
    # Defaults applied when the requirement keys are unset.
    assert summary["requirements"] == {
        "work_type": "fully remote",
        "eligibility": "Canada-eligible",
        "employment": ["full-time", "contract", "freelance"],
    }
    # Target-role fields come from the seeded DB built-ins.
    assert summary["target_titles"]
    assert summary["seniority_keywords"]
    assert summary["domains"]
    assert "inputs_hash" in summary


def test_comp_floor_added_when_configured(env):
    _, resume = env
    set_config("RESUME_FILE", str(resume))
    set_config("CANDIDATE_COMP_FLOOR_CAD", "180000")
    summary = build_summary()
    assert summary["requirements"]["comp_floor_cad"] == 180000


def test_missing_config_keys_produce_empty_strings(env):
    _, resume = env
    set_config("RESUME_FILE", str(resume))
    summary = build_summary()
    assert summary["headline"] == ""
    assert summary["notable"] == ""
    assert summary["years_experience"] == ""


def test_write_is_idempotent_on_unchanged_inputs(env):
    tmp_path, resume = env
    set_config("RESUME_FILE", str(resume))

    summary1, wrote1 = write_summary()
    assert wrote1 is True
    assert (tmp_path / "candidate-summary.json").exists()

    _, wrote2 = write_summary()
    assert wrote2 is False  # same inputs hash → no rewrite

    # Changing a config input flips the hash and triggers a rewrite.
    set_config("CANDIDATE_HEADLINE", "New Title")
    _, wrote3 = write_summary()
    assert wrote3 is True

    # --force rewrites even when unchanged.
    _, wrote4 = write_summary(force=True)
    assert wrote4 is True


def test_generated_date_alone_does_not_trigger_rewrite(env):
    _, resume = env
    set_config("RESUME_FILE", str(resume))
    summary, _ = write_summary()
    # inputs_hash must not include the daily `generated` field.
    assert "generated" in summary
    # Re-build: same hash regardless of when `generated` is stamped.
    assert build_summary()["inputs_hash"] == summary["inputs_hash"]


def test_one_time_import_migrates_existing_file(env, monkeypatch):
    tmp_path, _ = env
    (tmp_path / "candidate-summary.json").write_text(
        json.dumps(
            {
                "headline": "Imported Headline",
                "notable": "Imported Notable",
                "years_experience": 18,
                "requirements": {
                    "work_type": "remote only",
                    "eligibility": "Canada/US",
                    "employment": ["full-time", "contract"],
                    "comp_floor_cad": 200000,
                },
            }
        )
    )
    # First run with default import path on → migrates the fields into config.
    ensure_schema_and_seed()
    assert get_config_optional("CANDIDATE_HEADLINE") == "Imported Headline"
    assert get_config_optional("CANDIDATE_NOTABLE") == "Imported Notable"
    assert get_config_optional("CANDIDATE_YEARS_EXPERIENCE") == "18"
    assert get_config_optional("CANDIDATE_WORK_TYPE") == "remote only"
    assert get_config_optional("CANDIDATE_EMPLOYMENT") == "full-time,contract"
    assert get_config_optional("CANDIDATE_COMP_FLOOR_CAD") == "200000"


def test_cli_write_prints_json_and_writes(env):
    tmp_path, resume = env
    set_config("RESUME_FILE", str(resume))
    result = runner.invoke(cli.app, ["candidate-summary", "--write"])
    assert result.exit_code == 0, result.stdout
    summary = json.loads(result.stdout)
    assert summary["name"] == "Test User"
    assert (tmp_path / "candidate-summary.json").exists()
