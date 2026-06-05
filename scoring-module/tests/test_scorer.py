"""Tests for scoring_module.scorer"""

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from harness_db.models import make_engine

from scoring_module.scorer import (
    _age_modifier,
    _competition_modifier,
    _fetch_jd,
    _format_candidate_profile,
    _render_disqualifiers,
    _sanitize,
    _score_one,
    _upsert_company,
    score_batch,
    score_url,
)


@pytest.fixture(autouse=True)
def _no_real_embeddings(monkeypatch):
    """Keep tests hermetic: no real Ollama-backed dedup/indexing by default.

    Default is "no duplicate, indexing is a no-op"; the reuse test overrides
    scoring_module.scorer.find_duplicate to return a hit.
    """
    monkeypatch.setattr("scoring_module.scorer.find_duplicate", lambda *a, **k: None)
    monkeypatch.setattr("scoring_module.scorer.upsert_vector", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# _age_modifier — boundary tests for every branch
# ---------------------------------------------------------------------------


def _days_ago(n: int) -> str:
    return (date.today() - timedelta(days=n)).isoformat()


@pytest.mark.parametrize(
    "days,expected",
    [
        (0, 8),  # today
        (1, 8),
        (3, 8),  # boundary: ≤3 → +8
        (4, 4),  # boundary: 4 → +4
        (7, 4),  # boundary: ≤7 → +4
        (8, 0),  # boundary: 8 → 0
        (14, 0),  # boundary: ≤14 → 0
        (15, -5),  # boundary: 15 → -5
        (30, -5),  # boundary: ≤30 → -5
        (31, -12),  # boundary: 31 → -12
        (90, -12),
    ],
)
def test_age_modifier_boundaries(days, expected):
    assert _age_modifier(_days_ago(days)) == expected


def test_age_modifier_none():
    assert _age_modifier(None) == 0


def test_age_modifier_empty_string():
    assert _age_modifier("") == 0


def test_age_modifier_invalid_date():
    assert _age_modifier("not-a-date") == 0


# ---------------------------------------------------------------------------
# _competition_modifier — boundary tests for every branch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "count,expected",
    [
        (0, 5),  # < 25 → +5
        (1, 5),
        (24, 5),  # boundary: 24 → +5
        (25, 0),  # boundary: 25 → 0
        (100, 0),  # boundary: ≤100 → 0
        (101, -5),  # boundary: 101 → -5
        (200, -5),  # boundary: ≤200 → -5
        (201, -10),  # boundary: 201 → -10
        (500, -10),
    ],
)
def test_competition_modifier_boundaries(count, expected):
    assert _competition_modifier(count) == expected


def test_competition_modifier_none():
    assert _competition_modifier(None) == 0


# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_,expected",
    [
        ("Acme Corp", "acme-corp"),
        ("A&B Solutions, Inc.", "ab-solutions-inc"),
        ("  Company  ", "company"),
        ("Two  Words", "two-words"),
        ("Already-clean", "already-clean"),
        ("123 Numbers", "123-numbers"),
    ],
)
def test_sanitize(input_, expected):
    assert _sanitize(input_) == expected


# ---------------------------------------------------------------------------
# disqualifiers config
# ---------------------------------------------------------------------------


def test_render_disqualifiers_includes_name_modifier_examples():
    config = {
        "scoring_modifiers": [
            {"name": "Requires cert", "modifier": -40, "examples": ["AWS Certified", "CISSP"]},
            {"name": "Relocation", "modifier": -30, "examples": []},
        ]
    }
    text = _render_disqualifiers(config)
    assert "Requires cert (AWS Certified, CISSP): -40" in text
    assert "Relocation: -30" in text
    assert "No disqualifiers: 0" in text


def test_render_disqualifiers_empty_config():
    assert _render_disqualifiers({}) == "- No disqualifiers: 0"


# ---------------------------------------------------------------------------
# _format_candidate_profile — comp floor surfacing
# ---------------------------------------------------------------------------


def test_format_candidate_profile_includes_comp_floor_when_set():
    profile = {"requirements": {"work_type": "fully remote", "comp_floor_cad": 100000}}
    text = _format_candidate_profile(profile)
    assert "minimum compensation=CAD 100,000" in text


def test_format_candidate_profile_omits_comp_floor_when_absent():
    profile = {"requirements": {"work_type": "fully remote"}}
    text = _format_candidate_profile(profile)
    assert "minimum compensation" not in text


# Loading/seeding of disqualifiers.yaml now lives in harness_db and is covered by
# harness_db.tests.test_disqualifiers.


# ---------------------------------------------------------------------------
# _fetch_jd
# ---------------------------------------------------------------------------


def test_fetch_jd_strips_html_and_truncates():
    html = "<html><body>" + ("<p>word </p>" * 2000) + "</body></html>"
    mock_resp = MagicMock(status_code=200, text=html)
    with patch("scoring_module.scorer.httpx.get", return_value=mock_resp):
        result = _fetch_jd("https://example.com/job")
    assert result is not None
    assert "<" not in result
    assert len(result) <= 8000


def test_fetch_jd_returns_none_on_non_200():
    mock_resp = MagicMock(status_code=404)
    with patch("scoring_module.scorer.httpx.get", return_value=mock_resp):
        assert _fetch_jd("https://example.com/job") is None


def test_fetch_jd_returns_none_on_exception():
    with patch("scoring_module.scorer.httpx.get", side_effect=Exception("timeout")):
        assert _fetch_jd("https://example.com/job") is None


# ---------------------------------------------------------------------------
# _score_one helpers
# ---------------------------------------------------------------------------


def _api_response(
    base_score=78, disqualifier_modifier=0, notes="Good fit", dimension_scores=None
) -> MagicMock:
    """Build a mock Anthropic client that returns a given score response."""
    if dimension_scores is None:
        dimension_scores = {
            k: 8
            for k in (
                "technical_fit",
                "seniority_match",
                "domain_fit",
                "remote_canada_confirmed",
                "role_clarity",
            )
        }
    payload = {
        "dimension_scores": dimension_scores,
        "base_score": base_score,
        "disqualifier_modifier": disqualifier_modifier,
        "scoring_notes": notes,
    }
    block = MagicMock()
    block.text = json.dumps(payload)
    msg = MagicMock()
    msg.content = [block]
    client = MagicMock()
    client.messages.create.return_value = msg
    return client


def _posting(jd_text="x" * 600, post_date=None, applicant_count=None, **kwargs):
    """Build a minimal posting dict."""
    return {
        "url": "https://example.com/job/1",
        "title": "Principal Engineer",
        "company": "Acme Corp",
        "platform": "linkedin",
        "post_date": post_date,
        "applicant_count": applicant_count,
        "description_summary": "A software role",
        "job_description_text": jd_text,
        **kwargs,
    }


# ---------------------------------------------------------------------------
# _score_one — scoring math
# ---------------------------------------------------------------------------


def test_score_one_modifier_math():
    # base=80, today (+8 age), <25 applicants (+5), no disqualifier → modifier=13
    client = _api_response(base_score=80)
    result = _score_one(client, _posting(post_date=_days_ago(0), applicant_count=10))
    assert result["base_score"] == 80
    assert result["modifier"] == 13
    assert result["final_score"] == 93


def test_score_one_disqualifier_included_in_modifier():
    # cert required: disqualifier=-40; no age/competition modifiers
    client = _api_response(base_score=75, disqualifier_modifier=-40, notes="Requires AWS Certified")
    result = _score_one(client, _posting())
    assert result["modifier"] == -40
    assert result["final_score"] == 35


def test_score_one_clamps_to_100():
    client = _api_response(base_score=95)
    result = _score_one(client, _posting(post_date=_days_ago(0), applicant_count=10))
    assert result["final_score"] == 100


def test_score_one_clamps_to_1():
    # -65 disqualifier + -12 old post + -10 competitive = -87 net
    client = _api_response(base_score=20, disqualifier_modifier=-65)
    result = _score_one(
        client,
        _posting(
            post_date=_days_ago(60),
            applicant_count=300,
        ),
    )
    assert result["final_score"] == 1


# ---------------------------------------------------------------------------
# _score_one — JD fetch behaviour
# ---------------------------------------------------------------------------


def test_score_one_skips_fetch_when_jd_present():
    client = _api_response()
    with patch("scoring_module.scorer._fetch_jd") as mock_fetch:
        _score_one(client, _posting(jd_text="x" * 500))  # exactly 500 — still calls fetch
        # 500 is NOT < 500, so fetch should NOT be called
        mock_fetch.assert_not_called()


def test_score_one_fetches_when_jd_short():
    client = _api_response()
    fetched = "Full description " * 100
    with patch("scoring_module.scorer._fetch_jd", return_value=fetched) as mock_fetch:
        result = _score_one(client, _posting(jd_text="short"))  # 5 chars < 500
        mock_fetch.assert_called_once_with("https://example.com/job/1")
        assert result["job_description_text"] == fetched


def test_score_one_fetch_failure_uses_summary_and_penalises():
    client = _api_response(base_score=70)
    post = _posting(jd_text="", **{"description_summary": "A cloud role"})
    with patch("scoring_module.scorer._fetch_jd", return_value=None):
        result = _score_one(client, post)
    # fetch failed → modifier gets -5
    assert "[WebFetch failed" in result["scoring_notes"]
    assert result["modifier"] == -5
    assert result["final_score"] == 65  # 70 + (-5)
    assert result["job_description_text"] == "A cloud role"


# ---------------------------------------------------------------------------
# _score_one — API response edge cases
# ---------------------------------------------------------------------------


def test_score_one_invalid_json_uses_default():
    block = MagicMock()
    block.text = "not json {{{"
    msg = MagicMock()
    msg.content = [block]
    client = MagicMock()
    client.messages.create.return_value = msg

    result = _score_one(client, _posting())
    assert result["base_score"] == 50
    assert "JSON parse failed" in result["scoring_notes"]


def test_score_one_passes_cache_control_on_system_prompt():
    client = _api_response()
    _score_one(client, _posting())
    call_kwargs = client.messages.create.call_args
    system = call_kwargs.kwargs["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}


# ---------------------------------------------------------------------------
# score_batch — end-to-end with tmp DB and tmp files
# ---------------------------------------------------------------------------


def _make_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE postings (
            url TEXT PRIMARY KEY,
            title TEXT, company TEXT, platform TEXT,
            post_date TEXT, applicant_count INTEGER,
            status TEXT DEFAULT 'new',
            base_score INTEGER, modifier INTEGER, final_score INTEGER,
            scored_date TEXT, scoring_notes TEXT,
            dimension_scores TEXT, job_description_text TEXT,
            description_summary TEXT, location_note TEXT,
            first_seen TEXT, selected_date TEXT, employment_type TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE companies (
            name TEXT PRIMARY KEY,
            remote_confirmed INTEGER DEFAULT 0,
            canada_confirmed INTEGER DEFAULT 0,
            notes TEXT, researched_date TEXT, last_seen_date TEXT,
            careers_url TEXT, fetch_notes TEXT
        )
    """)
    conn.commit()
    conn.close()


def _insert_posting(db_path: Path, url: str, company: str, title: str, **cols) -> None:
    conn = sqlite3.connect(str(db_path))
    keys = ["url", "company", "title", "status", *cols.keys()]
    values = [url, company, title, "new", *cols.values()]
    placeholders = ", ".join("?" for _ in keys)
    conn.execute(
        f"INSERT INTO postings ({', '.join(keys)}) VALUES ({placeholders})",
        values,
    )
    conn.commit()
    conn.close()


def _company_row(db_path: Path, name: str):
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT remote_confirmed, canada_confirmed, last_seen_date FROM companies WHERE name = ?",
        (name,),
    ).fetchone()
    conn.close()
    return row


def test_score_batch_scores_and_updates_db(tmp_path):
    postings = [
        {
            "url": "https://example.com/job/1",
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "platform": "linkedin",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "A role",
            "job_description_text": "x" * 600,
        }
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    db_path = tmp_path / "test.db"
    _make_db(db_path)
    _insert_posting(db_path, "https://example.com/job/1", "Acme Corp", "Principal Engineer")

    client = _api_response(base_score=78)

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        count = score_batch(str(batch_file))

    assert count == 1

    # DB row updated to 'scored'
    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT status, base_score, final_score, scoring_notes FROM postings WHERE url = ?",
        ("https://example.com/job/1",),
    ).fetchone()
    conn.close()

    assert row[0] == "scored"
    assert row[1] == 78
    assert row[2] is not None
    assert row[3] == "Good fit"


def test_score_batch_falls_back_to_canonical_db_path(tmp_path):
    """With SQLITE_DB_PATH unset (DB_PATH None), the scorer resolves the
    canonical JOB_DATA_ROOT/jobs/postings.db via harness_db.config.get_db_path()."""
    postings = [
        {
            "url": "https://example.com/job/1",
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "platform": "linkedin",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "A role",
            "job_description_text": "x" * 600,
        }
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    db_path = tmp_path / "jobs" / "postings.db"
    db_path.parent.mkdir(parents=True)
    _make_db(db_path)
    _insert_posting(db_path, "https://example.com/job/1", "Acme Corp", "Principal Engineer")

    client = _api_response(base_score=78)

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", None),
        patch("scoring_module.scorer.get_db_path", return_value=db_path),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        count = score_batch(str(batch_file))

    assert count == 1

    conn = sqlite3.connect(str(db_path))
    status = conn.execute(
        "SELECT status FROM postings WHERE url = ?",
        ("https://example.com/job/1",),
    ).fetchone()[0]
    conn.close()
    assert status == "scored"


def test_score_batch_writes_report_file(tmp_path):
    postings = [
        {
            "url": "https://example.com/job/2",
            "title": "Staff Engineer",
            "company": "Beta Inc",
            "platform": "indeed",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "",
            "job_description_text": "x" * 600,
        }
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    db_path = tmp_path / "test.db"
    _make_db(db_path)
    _insert_posting(db_path, "https://example.com/job/2", "Beta Inc", "Staff Engineer")

    client = _api_response(base_score=65)

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        score_batch(str(batch_file))

    reports_dir = tmp_path / "jobs" / "reports"
    report_files = list(reports_dir.glob("beta-inc-*.json"))
    assert len(report_files) == 1

    report = json.loads(report_files[0].read_text())
    assert report["company"] == "Beta Inc"
    assert report["base_score"] == 65


def test_score_batch_returns_count_on_partial_failure(tmp_path):
    postings = [
        {
            "url": f"https://example.com/job/{i}",
            "title": "Engineer",
            "company": f"Co{i}",
            "platform": "linkedin",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "",
            "job_description_text": "x" * 600,
        }
        for i in range(3)
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    db_path = tmp_path / "test.db"
    _make_db(db_path)
    for i in range(3):
        _insert_posting(db_path, f"https://example.com/job/{i}", f"Co{i}", "Engineer")

    call_count = 0

    def flaky_create(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("API error")
        block = MagicMock()
        block.text = json.dumps(
            {
                "dimension_scores": {
                    k: 7
                    for k in (
                        "technical_fit",
                        "seniority_match",
                        "domain_fit",
                        "remote_canada_confirmed",
                        "role_clarity",
                    )
                },
                "base_score": 60,
                "disqualifier_modifier": 0,
                "scoring_notes": "ok",
            }
        )
        msg = MagicMock()
        msg.content = [block]
        return msg

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = flaky_create

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=mock_client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
        patch("scoring_module.scorer.MAX_RETRIES", 0),
    ):
        count = score_batch(str(batch_file))

    assert count == 2  # 1 failed, 2 succeeded


def test_score_batch_reuses_duplicate_score(tmp_path):
    """A posting whose JD near-duplicates an already-scored posting reuses that
    verdict and skips the LLM call entirely."""
    from harness_db.models import Base, Posting, make_engine
    from sqlalchemy.orm import Session

    db_path = tmp_path / "test.db"
    engine = make_engine(db_path)
    Base.metadata.create_all(engine)

    with Session(engine) as s:
        # Already-scored canonical posting (the duplicate target).
        s.add(
            Posting(
                url="https://example.com/job/canonical",
                title="Principal Engineer",
                company="Acme Corp",
                status="scored",
                base_score=80,
                modifier=0,
                final_score=80,
                scored_date="2026-01-01",
                scoring_notes="Strong fit",
                dimension_scores=json.dumps({"technical_fit": 8}),
                job_description_text="Canonical " + "x" * 400,
            )
        )
        # The repost we will score (different URL, same job).
        s.add(
            Posting(
                url="https://example.com/job/repost",
                title="Principal Engineer",
                company="Acme Corp",
                status="new",
            )
        )
        s.commit()

    postings = [
        {
            "url": "https://example.com/job/repost",
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "platform": "indeed",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "A role",
            "job_description_text": "Repost " + "y" * 400,
        }
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    client = _api_response(base_score=10)  # would yield 10 if the LLM were consulted

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
        patch(
            "scoring_module.scorer.find_duplicate",
            return_value=("https://example.com/job/canonical", 0.05),
        ),
    ):
        count = score_batch(str(batch_file))

    assert count == 1
    client.messages.create.assert_not_called()  # reused, no LLM call

    with Session(engine) as s:
        repost = s.get(Posting, "https://example.com/job/repost")
    assert repost.status == "scored"
    assert repost.base_score == 80  # reused canonical's 80, not the mock's 10
    assert repost.final_score == 80
    assert repost.scoring_notes.startswith("[reused from near-duplicate")


# ---------------------------------------------------------------------------
# _upsert_company — company-flag ratchet
# ---------------------------------------------------------------------------


def _result(company="Acme Corp", remote_canada_confirmed=10):
    return {
        "company": company,
        "dimension_scores": {"remote_canada_confirmed": remote_canada_confirmed},
    }


def test_upsert_company_sets_flags_when_confirmed(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)
    engine = make_engine(db_path)
    _upsert_company(engine, _result(remote_canada_confirmed=8))  # boundary: ≥8 confirms
    assert _company_row(db_path, "Acme Corp") == (1, 1, date.today().isoformat())


def test_upsert_company_unconfirmed_leaves_flags_zero(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)
    engine = make_engine(db_path)
    _upsert_company(engine, _result(remote_canada_confirmed=7))  # below 8
    assert _company_row(db_path, "Acme Corp") == (0, 0, date.today().isoformat())


def test_upsert_company_never_downgrades_existing_flag(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO companies (name, remote_confirmed, canada_confirmed, last_seen_date) "
        "VALUES ('Acme Corp', 1, 1, '2020-01-01')"
    )
    conn.commit()
    conn.close()

    engine = make_engine(db_path)
    _upsert_company(engine, _result(remote_canada_confirmed=2))  # a vaguer later posting
    # MAX() keeps the prior 1s; last_seen advances to today.
    assert _company_row(db_path, "Acme Corp") == (1, 1, date.today().isoformat())


def test_upsert_company_skips_blank_company(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)
    engine = make_engine(db_path)
    _upsert_company(engine, _result(company="   "))
    assert _company_row(db_path, "") is None


def test_upsert_company_is_best_effort_without_table(tmp_path, capsys):
    # A legacy DB with no companies table must not raise — just warn.
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE postings (url TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()
    engine = make_engine(db_path)
    _upsert_company(engine, _result())  # must not raise
    assert "could not ratchet company" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# score_batch / score_url — company-flag side effect
# ---------------------------------------------------------------------------


def test_score_batch_ratchets_company_flags(tmp_path):
    postings = [
        {
            "url": "https://example.com/job/1",
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "platform": "linkedin",
            "post_date": None,
            "applicant_count": None,
            "description_summary": "A role",
            "job_description_text": "x" * 600,
        }
    ]
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps(postings))

    db_path = tmp_path / "test.db"
    _make_db(db_path)
    _insert_posting(db_path, "https://example.com/job/1", "Acme Corp", "Principal Engineer")

    client = _api_response(base_score=78)  # default dims are all 8 → remote/Canada confirmed

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        score_batch(str(batch_file))

    assert _company_row(db_path, "Acme Corp") == (1, 1, date.today().isoformat())


def test_score_url_scores_single_posting_from_db(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)
    _insert_posting(
        db_path,
        "https://example.com/job/9",
        "Gamma LLC",
        "Staff Engineer",
        job_description_text="x" * 600,
        platform="indeed",
    )

    client = _api_response(base_score=82)

    with (
        patch("scoring_module.scorer.anthropic.Anthropic", return_value=client),
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        count = score_url("https://example.com/job/9")

    assert count == 1
    conn = sqlite3.connect(str(db_path))
    status, base = conn.execute(
        "SELECT status, base_score FROM postings WHERE url = ?",
        ("https://example.com/job/9",),
    ).fetchone()
    conn.close()
    assert status == "scored"
    assert base == 82
    assert _company_row(db_path, "Gamma LLC") == (1, 1, date.today().isoformat())


def test_score_url_returns_zero_for_unknown_url(tmp_path):
    db_path = tmp_path / "test.db"
    _make_db(db_path)

    with (
        patch("scoring_module.scorer.DB_PATH", str(db_path)),
        patch("scoring_module.scorer.JOB_DATA_ROOT", str(tmp_path)),
    ):
        assert score_url("https://example.com/job/absent") == 0
