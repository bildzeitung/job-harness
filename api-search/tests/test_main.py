"""Tests for the api_search CLI entry point — focused on the `append` command."""

import io
import json

import pytest

from api_search.__main__ import main


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    (tmp_path / "jobs").mkdir()
    return tmp_path


def test_append_from_file_merges_and_consumes_staging(env, capsys):
    batch = env / "jobs" / "linkedin-2026-06-02.batch.json"
    batch.write_text(json.dumps([{"url": "u1"}, {"url": "u1"}, {"url": "u2"}]))
    rc = main(["append", "linkedin", "--from", str(batch), "--date", "2026-06-02"])
    assert rc == 0
    assert not batch.exists()  # staging consumed on success
    canonical = json.loads((env / "jobs" / "linkedin-2026-06-02.json").read_text())
    assert [p["url"] for p in canonical["postings"]] == ["u1", "u2"]
    assert "[API-SEARCH:APPEND:LINKEDIN] +2 new" in capsys.readouterr().out


def test_append_accepts_payload_object_from_stdin(env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"postings": [{"url": "u9"}]})))
    rc = main(["append", "indeed", "--date", "2026-06-02"])
    assert rc == 0
    canonical = json.loads((env / "jobs" / "indeed-2026-06-02.json").read_text())
    assert [p["url"] for p in canonical["postings"]] == ["u9"]


def test_append_missing_from_file_reports_cleanly(env, capsys):
    rc = main(["append", "linkedin", "--from", str(env / "nope.json")])
    assert rc == 1
    assert "cannot read batch file" in capsys.readouterr().err


def test_append_invalid_json_returns_error(env, monkeypatch, capsys):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    rc = main(["append", "indeed"])
    assert rc == 1
    assert "invalid JSON batch" in capsys.readouterr().err


def test_append_without_platform_prints_usage(env, capsys):
    rc = main(["append"])
    assert rc == 2
    assert "append <platform>" in capsys.readouterr().err
