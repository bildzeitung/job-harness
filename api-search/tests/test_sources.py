"""Tests for api_search.sources — fetch generators and helpers."""

from api_search.sources import (
    SOURCES,
    _epoch_ms_to_date,
    _slug_to_name,
    _strip_html,
    fetch_adzuna,
    fetch_ashby,
    fetch_greenhouse,
    fetch_lever,
    fetch_remotive,
    load_config,
)
from tests.conftest import FakeResp, make_client

SUMMARY = {
    "target_titles": ["Principal Engineer"],
    "seniority_keywords": ["Principal"],
}


# ── helpers ─────────────────────────────────────────────────────────────────


def test_strip_html_unescapes_and_strips():
    assert _strip_html("&lt;p&gt;Hello   <b>world</b>&lt;/p&gt;") == "Hello world"


def test_strip_html_empty():
    assert _strip_html("") == ""


def test_slug_to_name():
    assert _slug_to_name("dbt-labs") == "Dbt Labs"
    assert _slug_to_name("weights_biases") == "Weights Biases"


def test_epoch_ms_to_date():
    # 2021-01-01T00:00:00Z = 1609459200000 ms
    assert _epoch_ms_to_date(1609459200000) == "2021-01-01"
    assert _epoch_ms_to_date(None) is None
    assert _epoch_ms_to_date("bad") is None


def test_config_has_slugs_for_board_sources():
    cfg = load_config()
    assert cfg["greenhouse"]["slugs"]
    assert cfg["lever"]["slugs"]
    assert cfg["ashby"]["slugs"]


def test_registry_platform_matches_name():
    for name, src in SOURCES.items():
        assert src.name == name


# ── fetch_adzuna ──────────────────────────────────────────────────────────────


def test_fetch_adzuna_normalizes_job(adzuna_env):
    payload = {
        "results": [
            {
                "title": "Principal Engineer",
                "company": {"display_name": "Acme Corp"},
                "redirect_url": "https://adzuna.ca/jobs/1",
                "created": "2026-05-25T12:00:00Z",
                "description": "Fully remote.",
            }
        ]
    }
    client = make_client(lambda url, params: FakeResp(payload))
    jobs = list(fetch_adzuna(client, SUMMARY, {}))
    assert jobs == [
        {
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "url": "https://adzuna.ca/jobs/1",
            "post_date": "2026-05-25",
            "location": "",
            "description": "Fully remote.",
        }
    ]


def test_fetch_adzuna_skips_failed_query(adzuna_env, capsys):
    def route(url, params):
        raise RuntimeError("timeout")

    client = make_client(route)
    assert list(fetch_adzuna(client, SUMMARY, {})) == []
    assert "[ADZUNA]" in capsys.readouterr().out


# ── fetch_greenhouse ──────────────────────────────────────────────────────────


def test_fetch_greenhouse_uses_meta_name_and_strips_content():
    cfg = {"slugs": ["acme"]}

    def route(url, params):
        if url.endswith("/jobs"):
            return FakeResp(
                {
                    "jobs": [
                        {
                            "title": "Staff Engineer",
                            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                            "updated_at": "2026-05-20T00:00:00Z",
                            "location": {"name": "Remote - Canada"},
                            "content": "&lt;p&gt;Remote role&lt;/p&gt;",
                        }
                    ]
                }
            )
        return FakeResp({"name": "Acme Corp"})

    jobs = list(fetch_greenhouse(make_client(route), SUMMARY, cfg))
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["location"] == "Remote - Canada"
    assert jobs[0]["description"] == "Remote role"
    assert jobs[0]["post_date"] == "2026-05-20"


def test_fetch_greenhouse_falls_back_to_slug_name_when_meta_fails():
    cfg = {"slugs": ["dbt-labs"]}

    def route(url, params):
        if url.endswith("/jobs"):
            return FakeResp({"jobs": [{"title": "X", "absolute_url": "u", "content": ""}]})
        return FakeResp({}, status=500)  # meta fails

    jobs = list(fetch_greenhouse(make_client(route), SUMMARY, cfg))
    assert jobs[0]["company"] == "Dbt Labs"


def test_fetch_greenhouse_skips_failed_board(capsys):
    cfg = {"slugs": ["acme"]}

    def route(url, params):
        if url.endswith("/jobs"):
            return FakeResp({}, status=500)
        return FakeResp({"name": "Acme"})

    assert list(fetch_greenhouse(make_client(route), SUMMARY, cfg)) == []
    assert "[GREENHOUSE]" in capsys.readouterr().out


# ── fetch_lever ───────────────────────────────────────────────────────────────


def test_fetch_lever_normalizes_posting():
    cfg = {"slugs": ["acme-co"]}
    payload = [
        {
            "text": "Principal Engineer",
            "hostedUrl": "https://jobs.lever.co/acme-co/1",
            "createdAt": 1609459200000,
            "categories": {"location": "Remote"},
            "descriptionPlain": "Remote senior role",
        }
    ]
    jobs = list(fetch_lever(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert jobs[0]["company"] == "Acme Co"
    assert jobs[0]["url"] == "https://jobs.lever.co/acme-co/1"
    assert jobs[0]["post_date"] == "2021-01-01"
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["description"] == "Remote senior role"


def test_fetch_lever_strips_html_when_no_plain():
    cfg = {"slugs": ["acme"]}
    payload = [
        {
            "text": "Staff Engineer",
            "hostedUrl": "u",
            "categories": {},
            "description": "<p>Remote</p>",
        }
    ]
    jobs = list(fetch_lever(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert jobs[0]["description"] == "Remote"
    assert jobs[0]["location"] == ""


def test_fetch_lever_skips_failed_board(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_lever(make_client(route), SUMMARY, {"slugs": ["acme"]})) == []
    assert "[LEVER]" in capsys.readouterr().out


# ── fetch_ashby ───────────────────────────────────────────────────────────────


def test_fetch_ashby_uses_slug_name_and_prefers_plain():
    cfg = {"slugs": ["acme-co"]}
    payload = {
        "jobs": [
            {
                "title": "Staff Engineer",
                "jobUrl": "https://jobs.ashbyhq.com/acme-co/1",
                "applyUrl": "https://jobs.ashbyhq.com/acme-co/1/application",
                "publishedAt": "2026-05-20T20:13:45.158+00:00",
                "location": "Remote - Canada",
                "isListed": True,
                "descriptionPlain": "Remote senior role",
                "descriptionHtml": "<p>Remote senior role</p>",
            }
        ]
    }
    jobs = list(fetch_ashby(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert len(jobs) == 1
    assert jobs[0]["company"] == "Acme Co"
    assert jobs[0]["url"] == "https://jobs.ashbyhq.com/acme-co/1"
    assert jobs[0]["post_date"] == "2026-05-20"
    assert jobs[0]["location"] == "Remote - Canada"
    assert jobs[0]["description"] == "Remote senior role"


def test_fetch_ashby_strips_html_when_no_plain_and_skips_unlisted():
    cfg = {"slugs": ["acme"]}
    payload = {
        "jobs": [
            {"title": "Hidden", "jobUrl": "u0", "isListed": False, "descriptionHtml": "<p>x</p>"},
            {
                "title": "Principal Engineer",
                "jobUrl": "u1",
                "descriptionHtml": "&lt;p&gt;Remote&lt;/p&gt;",
            },
        ]
    }
    jobs = list(fetch_ashby(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Principal Engineer"
    assert jobs[0]["description"] == "Remote"


def test_fetch_ashby_skips_failed_board(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_ashby(make_client(route), SUMMARY, {"slugs": ["acme"]})) == []
    assert "[ASHBY]" in capsys.readouterr().out


# ── fetch_remotive ────────────────────────────────────────────────────────────


def test_fetch_remotive_normalizes_and_strips_html():
    payload = {
        "jobs": [
            {
                "title": "Principal Engineer",
                "company_name": "Acme Corp ",
                "url": "https://remotive.com/remote-jobs/1",
                "publication_date": "2026-06-02T20:15:53",
                "candidate_required_location": "Worldwide",
                "description": "<p>Fully remote senior role</p>",
            }
        ]
    }
    jobs = list(fetch_remotive(make_client(lambda url, params: FakeResp(payload)), SUMMARY, {}))
    assert jobs == [
        {
            "title": "Principal Engineer",
            "company": "Acme Corp",
            "url": "https://remotive.com/remote-jobs/1",
            "post_date": "2026-06-02",
            "location": "Worldwide",
            "description": "Fully remote senior role",
        }
    ]


def test_fetch_remotive_skips_failed_query(capsys):
    def route(url, params):
        raise RuntimeError("timeout")

    assert list(fetch_remotive(make_client(route), SUMMARY, {})) == []
    assert "[REMOTIVE]" in capsys.readouterr().out
