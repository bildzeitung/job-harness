"""Tests for adzuna_search.search"""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adzuna_search.search import (
    _is_canada_eligible,
    _is_junior,
    _is_remote,
    _is_senior,
    load_candidate_summary,
    queries_from_summary,
    search,
    seniority_keywords_from_summary,
)

# ── fixtures ──────────────────────────────────────────────────────────────────

SUMMARY = {
    "target_titles": ["Principal Engineer", "Staff Engineer", "Cloud Architect"],
    "seniority_keywords": ["Principal", "Staff", "Cloud Architect", "Senior Staff"],
}


def _write_summary(tmp_path: Path, data: dict = SUMMARY) -> Path:
    p = tmp_path / "candidate-summary.json"
    p.write_text(json.dumps(data))
    return tmp_path


def _mock_job(
    url: str = "https://adzuna.ca/jobs/1",
    title: str = "Principal Engineer",
    company: str = "Acme Corp",
    description: str = "Fully remote position in Canada.",
    created: str = "2026-05-25T00:00:00Z",
) -> dict:
    return {
        "redirect_url": url,
        "title": title,
        "company": {"display_name": company},
        "description": description,
        "created": created,
    }


def _mock_client(jobs: list[dict]):
    """Return a patched httpx.Client whose get() yields the given jobs."""
    resp = MagicMock()
    resp.json.return_value = {"results": jobs}
    resp.raise_for_status.return_value = None

    client = MagicMock()
    client.get.return_value = resp
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    return client


# ── load_candidate_summary ────────────────────────────────────────────────────

def test_load_raises_when_env_unset(monkeypatch):
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="JOB_DATA_ROOT"):
        load_candidate_summary()


def test_load_raises_when_file_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    with pytest.raises(FileNotFoundError):
        load_candidate_summary()


def test_load_returns_parsed_dict(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_DATA_ROOT", str(_write_summary(tmp_path)))
    result = load_candidate_summary()
    assert result["target_titles"] == SUMMARY["target_titles"]


# ── queries_from_summary ──────────────────────────────────────────────────────

def test_queries_appends_remote():
    queries = queries_from_summary(SUMMARY)
    assert all(q.endswith(" remote") for q in queries)


def test_queries_one_per_title():
    queries = queries_from_summary(SUMMARY)
    assert len(queries) == len(SUMMARY["target_titles"])


def test_queries_includes_each_title():
    queries = queries_from_summary(SUMMARY)
    for title in SUMMARY["target_titles"]:
        assert any(title in q for q in queries)


# ── seniority_keywords_from_summary ──────────────────────────────────────────

def test_seniority_keywords_are_lowercase():
    keywords = seniority_keywords_from_summary(SUMMARY)
    assert all(kw == kw.lower() for kw in keywords)


def test_seniority_keywords_count():
    keywords = seniority_keywords_from_summary(SUMMARY)
    assert len(keywords) == len(SUMMARY["seniority_keywords"])


# ── filter predicates ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Fully remote role", True),
    ("Remote-first company", True),
    ("On-site in Toronto", False),
    ("Hybrid work arrangement", False),
])
def test_is_remote(text, expected):
    assert _is_remote(text) is expected


@pytest.mark.parametrize("title,expected", [
    ("Principal Software Engineer", True),
    ("Staff Engineer", True),
    ("Cloud Architect", True),
    ("Senior Staff Engineer", True),
    ("Software Developer II", False),
    ("Junior Engineer", False),
])
def test_is_senior(title, expected):
    keywords = seniority_keywords_from_summary(SUMMARY)
    assert _is_senior(title, keywords) is expected


@pytest.mark.parametrize("title,expected", [
    ("Junior Software Engineer", True),
    ("Intern, Platform Team", True),
    ("Entry level developer", True),
    ("Entry-Level Engineer", True),
    ("Senior Engineer", False),
    ("Principal Architect", False),
])
def test_is_junior(title, expected):
    assert _is_junior(title) is expected


@pytest.mark.parametrize("text,expected", [
    ("Open to Canadian candidates", True),
    ("Remote, worldwide", True),
    ("US only — must have US work authorization", False),
    ("US citizens only", False),
    ("Must be located in US", False),
])
def test_is_canada_eligible(text, expected):
    assert _is_canada_eligible(text) is expected


# ── search ────────────────────────────────────────────────────────────────────

@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_DATA_ROOT", str(_write_summary(tmp_path)))
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_API_KEY", "test_key")


def test_search_returns_matching_job(env):
    client = _mock_client([_mock_job()])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote"])
    assert len(results) == 1
    assert results[0]["title"] == "Principal Engineer"
    assert results[0]["company"] == "Acme Corp"


def test_search_filters_non_remote(env):
    job = _mock_job(description="On-site role in Toronto.")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote"])
    assert results == []


def test_search_filters_non_senior(env):
    job = _mock_job(title="Software Developer II", description="Remote role.")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["software developer remote"])
    assert results == []


def test_search_filters_junior(env):
    job = _mock_job(title="Junior Engineer", description="Remote role.")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["junior engineer remote"])
    assert results == []


def test_search_filters_us_only(env):
    job = _mock_job(description="Remote role. US citizens only.")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote"])
    assert results == []


def test_search_deduplicates_across_queries(env):
    job = _mock_job(url="https://adzuna.ca/jobs/1")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote", "staff engineer remote"])
    assert len(results) == 1


def test_search_post_date_truncated_to_date(env):
    job = _mock_job(created="2026-05-25T12:34:56Z")
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote"])
    assert results[0]["post_date"] == "2026-05-25"


def test_search_description_truncated_to_300(env):
    long_desc = "remote " + "x" * 400
    job = _mock_job(description=long_desc)
    client = _mock_client([job])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["principal engineer remote"])
    assert len(results[0]["description_summary"]) == 300


def test_search_skips_failed_query_and_continues(env, capsys):
    good_job = _mock_job(url="https://adzuna.ca/jobs/good")

    resp_ok = MagicMock()
    resp_ok.json.return_value = {"results": [good_job]}
    resp_ok.raise_for_status.return_value = None

    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    # First query raises, second succeeds
    client.get.side_effect = [Exception("timeout"), resp_ok]

    with patch("adzuna_search.search.httpx.Client", return_value=client):
        results = search(queries=["bad query", "principal engineer remote"])

    assert len(results) == 1
    assert "[ADZUNA]" in capsys.readouterr().out


def test_search_uses_queries_from_summary_when_none_given(env):
    client = _mock_client([])
    with patch("adzuna_search.search.httpx.Client", return_value=client):
        search()
    # One API call per title in SUMMARY["target_titles"]
    assert client.get.call_count == len(SUMMARY["target_titles"])
