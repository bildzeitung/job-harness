"""Tests for api_search.candidate."""

import json
from pathlib import Path

import pytest

from api_search.candidate import (
    load_candidate_summary,
    queries_from_summary,
    seniority_keywords_from_summary,
)

SUMMARY = {
    "target_titles": ["Principal Engineer", "Staff Engineer", "Cloud Architect"],
    "seniority_keywords": ["Principal", "Staff", "Cloud Architect", "Senior Staff"],
}


def _write_summary(tmp_path: Path, data: dict = SUMMARY) -> Path:
    (tmp_path / "candidate-summary.json").write_text(json.dumps(data))
    return tmp_path


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
    assert load_candidate_summary()["target_titles"] == SUMMARY["target_titles"]


def test_queries_appends_remote_one_per_title():
    queries = queries_from_summary(SUMMARY)
    assert len(queries) == len(SUMMARY["target_titles"])
    assert all(q.endswith(" remote") for q in queries)
    for title in SUMMARY["target_titles"]:
        assert any(title in q for q in queries)


def test_seniority_keywords_are_lowercase():
    keywords = seniority_keywords_from_summary(SUMMARY)
    assert keywords == [kw.lower() for kw in SUMMARY["seniority_keywords"]]
