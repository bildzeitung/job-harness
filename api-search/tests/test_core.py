"""Tests for api_search.core — the shared filter/dedup/shape/output pipeline."""

import json
from pathlib import Path

import pytest

from api_search.core import append_postings, dedup_by_url, run, write_output
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


def test_run_filters_via_prefilter_title_term(env, monkeypatch):
    # "internship" is a disqualifiers.yaml prefilter title_term — dropped even
    # though the title also matches a seniority keyword.
    _patch_adzuna(monkeypatch, [_adzuna_job(title="Principal Engineer Internship")])
    assert run("adzuna") == []


def test_run_filters_via_prefilter_description_phrase(env, monkeypatch):
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


# ── dedup_by_url ──────────────────────────────────────────────────────────────


def test_dedup_by_url_keeps_first_and_drops_blanks():
    out = dedup_by_url(
        [
            {"url": "a", "n": 1},
            {"url": "a", "n": 2},  # dup → dropped
            {"url": "", "n": 3},  # blank → dropped
            {"n": 4},  # missing → dropped
            {"url": "b", "n": 5},
        ]
    )
    assert out == [{"url": "a", "n": 1}, {"url": "b", "n": 5}]


# ── append_postings ───────────────────────────────────────────────────────────


def _read_postings(env, platform, batch_date):
    return json.loads((env / "jobs" / f"{platform}-{batch_date}.json").read_text())["postings"]


def test_append_postings_writes_when_no_existing_file(env):
    batch = [{"url": "u1", "title": "A"}, {"url": "u2", "title": "B"}]
    result = append_postings("linkedin", batch, batch_date="2026-06-01")
    assert result["added"] == 2
    assert result["total"] == 2
    assert result["skipped"] == 0
    assert result["path"] == str(env / "jobs" / "linkedin-2026-06-01.json")
    payload = json.loads(Path(result["path"]).read_text())
    assert payload["platform"] == "linkedin"
    assert payload["total_found"] == 2
    assert [p["url"] for p in payload["postings"]] == ["u1", "u2"]


def test_append_postings_merges_and_dedups_against_existing(env):
    append_postings("indeed", [{"url": "u1", "title": "A"}], batch_date="2026-06-01")
    result = append_postings(
        "indeed",
        [{"url": "u1", "title": "A-updated"}, {"url": "u2", "title": "B"}],
        batch_date="2026-06-01",
    )
    assert result["added"] == 1  # only u2 is new
    assert result["skipped"] == 1  # u1 already present
    assert result["total"] == 2
    postings = _read_postings(env, "indeed", "2026-06-01")
    # Existing record wins on collision (keeps original title).
    assert postings[0] == {"url": "u1", "title": "A"}
    assert [p["url"] for p in postings] == ["u1", "u2"]


def test_append_postings_dedups_within_new_batch(env):
    result = append_postings(
        "research",
        [{"url": "u1"}, {"url": "u1"}, {"url": ""}, {"url": "u2"}],
        batch_date="2026-06-01",
    )
    assert result["added"] == 2
    assert [p["url"] for p in _read_postings(env, "research", "2026-06-01")] == ["u1", "u2"]


def test_append_postings_tolerates_corrupt_existing_file(env):
    (env / "jobs").mkdir(parents=True, exist_ok=True)
    (env / "jobs" / "ziprecruiter-2026-06-01.json").write_text("{ not json")
    result = append_postings("ziprecruiter", [{"url": "u1"}], batch_date="2026-06-01")
    assert result["added"] == 1
    assert result["total"] == 1


@pytest.mark.parametrize("bad", ['{"postings": null}', '{"postings": 42}', "[1, 2, 3]"])
def test_append_postings_tolerates_non_list_postings(env, bad):
    # A file that parses but whose "postings" is null/non-list (or a top-level
    # list) must be treated as empty, not crash.
    (env / "jobs").mkdir(parents=True, exist_ok=True)
    (env / "jobs" / "indeed-2026-06-01.json").write_text(bad)
    result = append_postings("indeed", [{"url": "u1"}], batch_date="2026-06-01")
    assert result["added"] == 1
    assert [p["url"] for p in _read_postings(env, "indeed", "2026-06-01")] == ["u1"]


def test_append_postings_requires_job_data_root(monkeypatch):
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="JOB_DATA_ROOT"):
        append_postings("linkedin", [])


# ── append_postings prefilter (A1) ────────────────────────────────────────────


def test_append_postings_drops_prefilter_disqualified(env):
    # "internship" is a default prefilter title_term; the geography phrase is a
    # default description_phrase. Both incoming postings must be dropped while
    # the clean one survives, and counted under `disqualified` not `skipped`.
    batch = [
        {"url": "u1", "title": "Principal Engineer"},
        {"url": "u2", "title": "Principal Engineer Internship"},
        {
            "url": "u3",
            "title": "Staff Engineer",
            "description_summary": "Remote. US citizens only.",
        },
    ]
    result = append_postings("research", batch, batch_date="2026-06-01")
    assert result["added"] == 1
    assert result["disqualified"] == 2
    assert result["skipped"] == 0
    assert [p["url"] for p in _read_postings(env, "research", "2026-06-01")] == ["u1"]


def test_append_postings_does_not_refilter_existing(env):
    # Seed a file that already contains a posting which would match the prefilter
    # (simulating one appended before a rule existed). It must be preserved — only
    # incoming postings are filtered.
    (env / "jobs").mkdir(parents=True, exist_ok=True)
    (env / "jobs" / "linkedin-2026-06-01.json").write_text(
        json.dumps(
            {
                "search_date": "2026-06-01",
                "platform": "linkedin",
                "total_found": 1,
                "postings": [{"url": "old", "title": "Principal Engineer Internship"}],
            }
        )
    )
    result = append_postings(
        "linkedin", [{"url": "new", "title": "Staff Engineer"}], batch_date="2026-06-01"
    )
    assert result["added"] == 1
    assert result["disqualified"] == 0
    assert [p["url"] for p in _read_postings(env, "linkedin", "2026-06-01")] == ["old", "new"]


# ── append_postings disqualified sidecar ──────────────────────────────────────


def _read_sidecar(env, platform, batch_date):
    return json.loads((env / "jobs" / f"{platform}-{batch_date}.disqualified.json").read_text())


def test_append_postings_logs_drops_to_sidecar_with_matched_rule(env):
    batch = [
        {"url": "u1", "title": "Principal Engineer"},
        {"url": "u2", "title": "Principal Engineer Internship"},
    ]
    append_postings("research", batch, batch_date="2026-06-01")
    sidecar = _read_sidecar(env, "research", "2026-06-01")
    assert sidecar["platform"] == "research"
    assert sidecar["search_date"] == "2026-06-01"
    assert sidecar["total_dropped"] == 1
    [dropped] = sidecar["postings"]
    assert dropped["url"] == "u2"
    assert dropped["title"] == "Principal Engineer Internship"  # full posting preserved
    assert "internship" in dropped["matched_rule"]  # "category: value" audit trail


def test_append_postings_sidecar_merges_across_appends(env):
    append_postings(
        "research", [{"url": "u2", "title": "Software internship program"}], batch_date="2026-06-01"
    )
    append_postings(
        "research",
        [
            {"url": "u2", "title": "Software internship program"},  # dup → kept once
            {"url": "u3", "title": "Engineering internship"},
        ],
        batch_date="2026-06-01",
    )
    sidecar = _read_sidecar(env, "research", "2026-06-01")
    assert sidecar["total_dropped"] == 2
    assert [p["url"] for p in sidecar["postings"]] == ["u2", "u3"]


def test_append_postings_writes_no_sidecar_when_clean(env):
    append_postings("linkedin", [{"url": "u1", "title": "Staff Engineer"}], batch_date="2026-06-01")
    assert not (env / "jobs" / "linkedin-2026-06-01.disqualified.json").exists()
