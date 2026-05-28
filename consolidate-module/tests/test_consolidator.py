"""Tests for consolidate_module.consolidator."""

import json

import pytest
from harness_db.models import Base, Company, CompanyPosting, Posting, make_engine
from sqlalchemy import select
from sqlalchemy.orm import Session

from consolidate_module.consolidator import (
    PLATFORMS,
    _dedup,
    _load_platform_file,
    _write_audit_log,
    consolidate,
)

# ── _load_platform_file ────────────────────────────────────────────────────────


def test_load_missing_file_returns_empty(tmp_path):
    assert _load_platform_file(tmp_path, "adzuna", "2026-05-28") == []


def test_load_dict_envelope(tmp_path):
    (tmp_path / "adzuna-2026-05-28.json").write_text(
        json.dumps({"postings": [{"url": "u1", "title": "T"}]})
    )
    out = _load_platform_file(tmp_path, "adzuna", "2026-05-28")
    assert out == [{"url": "u1", "title": "T", "platform": "adzuna"}]


def test_load_raw_list(tmp_path):
    (tmp_path / "research-2026-05-28.json").write_text(json.dumps([{"url": "u1"}]))
    out = _load_platform_file(tmp_path, "research", "2026-05-28")
    assert out == [{"url": "u1", "platform": "research"}]


def test_load_preserves_existing_platform(tmp_path):
    (tmp_path / "adzuna-2026-05-28.json").write_text(
        json.dumps([{"url": "u1", "platform": "lever"}])
    )
    out = _load_platform_file(tmp_path, "adzuna", "2026-05-28")
    assert out[0]["platform"] == "lever"


def test_load_bad_json_warns_and_returns_empty(tmp_path, capsys):
    (tmp_path / "adzuna-2026-05-28.json").write_text("{not json")
    assert _load_platform_file(tmp_path, "adzuna", "2026-05-28") == []
    assert "[WARN]" in capsys.readouterr().err


# ── _dedup ──────────────────────────────────────────────────────────────────────


def test_dedup_removes_existing_and_within_batch():
    raw = [
        {"url": "a"},
        {"url": "b"},
        {"url": "a"},  # within-batch dup
        {"url": "c"},  # already in DB
        {"url": None},  # skipped, no url
        {},  # skipped, no url
    ]
    deduped, removed_existing, removed_within = _dedup(raw, existing_urls={"c"})
    assert [p["url"] for p in deduped] == ["a", "b"]
    assert removed_existing == 1
    assert removed_within == 1


def test_dedup_keeps_first_occurrence():
    raw = [{"url": "a", "title": "first"}, {"url": "a", "title": "second"}]
    deduped, _, _ = _dedup(raw, existing_urls=set())
    assert deduped == [{"url": "a", "title": "first"}]


# ── _write_audit_log ──────────────────────────────────────────────────────────


def test_write_audit_log_structure(tmp_path):
    out = tmp_path / "nested" / "search-2026-05-28.json"
    deduped = [{"url": "u1", "title": "T", "company": "Acme", "platform": "adzuna"}]
    _write_audit_log(out, "2026-05-28", {"adzuna": 1}, deduped)

    payload = json.loads(out.read_text())
    assert payload["search_date"] == "2026-05-28"
    assert payload["total_found"] == 1
    # every known platform is represented, missing ones default to 0
    assert set(payload["by_platform"]) == set(PLATFORMS)
    assert payload["by_platform"]["adzuna"] == 1
    assert payload["by_platform"]["lever"] == 0
    assert payload["postings"][0]["url"] == "u1"


# ── consolidate (end-to-end) ────────────────────────────────────────────────────


@pytest.fixture
def db_env(monkeypatch, tmp_path):
    root = tmp_path
    jobs = root / "jobs"
    jobs.mkdir()
    db_path = root / "postings.db"
    monkeypatch.setenv("JOB_DATA_ROOT", str(root))
    monkeypatch.setenv("SQLITE_DB_PATH", str(db_path))
    # Create schema the way the live pipeline would have.
    Base.metadata.create_all(make_engine(db_path))
    return root, jobs, db_path


def test_consolidate_inserts_and_dedups(db_env):
    root, jobs, db_path = db_env

    # Pre-seed one posting so dedup-against-DB has something to remove.
    engine = make_engine(db_path)
    with Session(engine) as s:
        s.add(Posting(url="https://x/existing", title="Old", status="new"))
        s.commit()

    (jobs / "adzuna-2026-05-28.json").write_text(
        json.dumps(
            {
                "postings": [
                    {"url": "https://x/1", "title": "Principal Eng", "company": "Acme"},
                    {"url": "https://x/existing", "title": "Dup of DB", "company": "Acme"},
                ]
            }
        )
    )
    (jobs / "lever-2026-05-28.json").write_text(
        json.dumps([{"url": "https://x/2", "title": "Staff Eng", "company": "Beta"}])
    )

    inserted = consolidate("2026-05-28")
    assert inserted == 2  # x/1 and x/2; x/existing dropped as already-in-DB

    with Session(engine) as s:
        urls = {row[0] for row in s.execute(select(Posting.url)).all()}
        assert urls == {"https://x/existing", "https://x/1", "https://x/2"}

        new_posting = s.get(Posting, "https://x/1")
        assert new_posting.platform == "adzuna"
        assert new_posting.first_seen == "2026-05-28"
        assert new_posting.status == "new"

        companies = {row[0] for row in s.execute(select(Company.name)).all()}
        assert {"Acme", "Beta"} <= companies

        links = {
            row[0]: row[1]
            for row in s.execute(select(CompanyPosting.url, CompanyPosting.company_name)).all()
        }
        assert links["https://x/1"] == "Acme"
        assert links["https://x/2"] == "Beta"

    audit = json.loads((jobs / "search-2026-05-28.json").read_text())
    assert audit["total_found"] == 2
    assert audit["by_platform"]["adzuna"] == 2  # raw count before dedup
    assert audit["by_platform"]["lever"] == 1


def test_consolidate_preserves_existing_company_enrichment(db_env):
    root, jobs, db_path = db_env

    engine = make_engine(db_path)
    with Session(engine) as s:
        s.add(Company(name="Acme", canada_confirmed=True, notes="enriched"))
        s.commit()

    (jobs / "adzuna-2026-05-28.json").write_text(
        json.dumps([{"url": "https://x/1", "title": "Principal", "company": "Acme"}])
    )

    consolidate("2026-05-28")

    with Session(engine) as s:
        acme = s.get(Company, "Acme")
        # ON CONFLICT DO NOTHING must not clobber prior enrichment.
        assert acme.canada_confirmed is True
        assert acme.notes == "enriched"


def test_consolidate_skips_blank_company(db_env):
    root, jobs, db_path = db_env
    (jobs / "adzuna-2026-05-28.json").write_text(
        json.dumps([{"url": "https://x/1", "title": "Principal", "company": ""}])
    )

    consolidate("2026-05-28")

    engine = make_engine(db_path)
    with Session(engine) as s:
        assert s.execute(select(Company.name)).all() == []
        assert s.execute(select(CompanyPosting.url)).all() == []
        assert s.get(Posting, "https://x/1") is not None
