"""Tests for api_search.core — the shared filter/dedup/shape/output pipeline."""

import json
from pathlib import Path

import pytest

from api_search.core import run, write_output
from tests.conftest import FakeResp, make_client

SUMMARY = {
    "target_titles": ["Principal Engineer", "Staff Engineer"],
    "seniority_keywords": ["Principal", "Staff"],
}


@pytest.fixture
def env(monkeypatch, tmp_path):
    (tmp_path / "candidate-summary.json").write_text(json.dumps(SUMMARY))
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_API_KEY", "key")
    return tmp_path


def _adzuna_job(url="https://adzuna.ca/jobs/1", title="Principal Engineer", desc="Fully remote."):
    return {
        "title": title,
        "company": {"display_name": "Acme"},
        "redirect_url": url,
        "created": "2026-05-25T00:00:00Z",
        "description": desc,
    }


def _patch_adzuna(monkeypatch, jobs):
    client = make_client(lambda url, params: FakeResp({"results": jobs}))
    monkeypatch.setattr("api_search.core.httpx.Client", lambda *a, **k: client)
    return client


def test_run_rejects_unknown_source(env):
    with pytest.raises(ValueError, match="Unknown source"):
        run("monster")


def test_run_shapes_record(env, monkeypatch):
    _patch_adzuna(monkeypatch, [_adzuna_job()])
    results = run("adzuna")
    assert len(results) == 1
    r = results[0]
    assert r["platform"] == "adzuna"
    assert r["employment_type"] == "full-time"
    assert r["location_note"] == "Remote, Canada"
    assert r["applicant_count"] is None
    assert r["job_description_text"] == "Fully remote."
    assert r["description_summary"] == "Fully remote."


def test_run_filters_non_remote(env, monkeypatch):
    _patch_adzuna(monkeypatch, [_adzuna_job(desc="On-site in Toronto.")])
    assert run("adzuna") == []


def test_run_filters_non_senior(env, monkeypatch):
    _patch_adzuna(monkeypatch, [_adzuna_job(title="Software Developer II")])
    assert run("adzuna") == []


def test_run_filters_junior(env, monkeypatch):
    _patch_adzuna(monkeypatch, [_adzuna_job(title="Junior Principal")])
    assert run("adzuna") == []


def test_run_filters_us_only(env, monkeypatch):
    _patch_adzuna(monkeypatch, [_adzuna_job(desc="Remote. US citizens only.")])
    assert run("adzuna") == []


def test_run_dedups_by_url(env, monkeypatch):
    # Same job returned for every query → one result.
    _patch_adzuna(monkeypatch, [_adzuna_job()])
    assert len(run("adzuna")) == 1


def test_run_truncates_long_description(env, monkeypatch):
    long_desc = "remote " + "x" * 9000
    _patch_adzuna(monkeypatch, [_adzuna_job(desc=long_desc)])
    r = run("adzuna")[0]
    assert len(r["description_summary"]) == 300
    assert len(r["job_description_text"]) == 8000


def test_write_output_writes_platform_file(env):
    results = [{"title": "X", "url": "u"}]
    path = write_output("greenhouse", results, batch_date="2026-05-28")
    assert path == env / "jobs" / "greenhouse-2026-05-28.json"
    payload = json.loads(Path(path).read_text())
    assert payload == {
        "search_date": "2026-05-28",
        "platform": "greenhouse",
        "total_found": 1,
        "postings": results,
    }


def test_write_output_requires_job_data_root(monkeypatch):
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="JOB_DATA_ROOT"):
        write_output("adzuna", [])
