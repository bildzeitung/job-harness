"""Tests for api_search.sources — fetch generators and helpers."""

from api_search.sources import (
    SOURCES,
    _canada_eligible,
    _epoch_ms_to_date,
    _rfc822_to_date,
    _slug_to_name,
    _strip_html,
    fetch_adzuna,
    fetch_ashby,
    fetch_greenhouse,
    fetch_himalayas,
    fetch_lever,
    fetch_recruitee,
    fetch_remotive,
    fetch_workable,
    fetch_wwr,
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
    assert cfg["workable"]["slugs"]
    assert cfg["recruitee"]["slugs"]
    assert cfg["wwr"]["categories"]


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


def test_fetch_adzuna_retries_on_429(adzuna_env, monkeypatch, capsys):
    # The free tier rate-limits; a 429 is transient and must be retried, not dropped.
    monkeypatch.setattr("api_search.sources.time.sleep", lambda _s: None)
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
    calls = {"n": 0}

    def route(url, params):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResp({}, status=429, headers={"Retry-After": "0"})
        return FakeResp(payload)

    client = make_client(route)
    jobs = list(fetch_adzuna(client, SUMMARY, {}))
    assert calls["n"] == 2  # retried after the 429
    assert [j["url"] for j in jobs] == ["https://adzuna.ca/jobs/1"]
    assert "429" in capsys.readouterr().out


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


# ── fetch_workable ────────────────────────────────────────────────────────────


def test_fetch_workable_uses_account_name_and_remote_flag():
    cfg = {"slugs": ["acme"]}
    payload = {
        "name": "Acme Corp",
        "jobs": [
            {
                "title": "Staff Engineer",
                "url": "https://apply.workable.com/j/ABC123",
                "shortlink": "https://apply.workable.com/j/ABC123",
                "published_on": "2026-06-02",
                "telecommuting": True,
                "city": "Halifax",
                "country": "Canada",
                "description": "<p>Senior role</p>",
            }
        ],
    }
    jobs = list(fetch_workable(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["url"] == "https://apply.workable.com/j/ABC123"
    assert jobs[0]["post_date"] == "2026-06-02"
    assert jobs[0]["location"] == "Remote"
    assert jobs[0]["description"] == "Senior role"


def test_fetch_workable_builds_location_when_not_remote():
    cfg = {"slugs": ["acme"]}
    payload = {
        "name": "Acme",
        "jobs": [
            {
                "title": "X",
                "url": "u",
                "telecommuting": False,
                "city": "Berlin",
                "country": "Germany",
                "description": "",
            }
        ],
    }
    jobs = list(fetch_workable(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert jobs[0]["location"] == "Berlin Germany"


def test_fetch_workable_skips_failed_board(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_workable(make_client(route), SUMMARY, {"slugs": ["acme"]})) == []
    assert "[WORKABLE]" in capsys.readouterr().out


# ── fetch_recruitee ───────────────────────────────────────────────────────────


def test_fetch_recruitee_normalizes_and_folds_remote_flag():
    cfg = {"slugs": ["acme"]}
    payload = {
        "offers": [
            {
                "title": "Principal Engineer",
                "careers_url": "https://jobs.acme.com/o/principal-engineer",
                "published_at": "2026-06-02 10:10:41 UTC",
                "status": "published",
                "remote": True,
                "location": "Utrecht, Netherlands",
                "company_name": "Acme",
                "description": "<p>Remote senior role</p>",
            }
        ]
    }
    jobs = list(fetch_recruitee(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["url"] == "https://jobs.acme.com/o/principal-engineer"
    assert jobs[0]["post_date"] == "2026-06-02"
    assert jobs[0]["location"] == "Remote Utrecht, Netherlands"
    assert jobs[0]["description"] == "Remote senior role"


def test_fetch_recruitee_skips_unpublished():
    cfg = {"slugs": ["acme"]}
    payload = {
        "offers": [
            {"title": "Draft", "careers_url": "u0", "status": "draft", "description": ""},
            {"title": "Live", "careers_url": "u1", "status": "published", "description": ""},
        ]
    }
    jobs = list(fetch_recruitee(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert [j["title"] for j in jobs] == ["Live"]


def test_fetch_recruitee_skips_failed_board(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_recruitee(make_client(route), SUMMARY, {"slugs": ["acme"]})) == []
    assert "[RECRUITEE]" in capsys.readouterr().out


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
            "location": "Remote — Worldwide",
            "description": "Fully remote senior role",
        }
    ]


def test_fetch_remotive_drops_non_canada_eligible():
    payload = {
        "jobs": [
            {
                "title": "A",
                "url": "u1",
                "candidate_required_location": "USA Only",
                "description": "",
            },
            {"title": "B", "url": "u2", "candidate_required_location": "Canada", "description": ""},
        ]
    }
    jobs = list(fetch_remotive(make_client(lambda url, params: FakeResp(payload)), SUMMARY, {}))
    assert [j["title"] for j in jobs] == ["B"]


def test_fetch_remotive_skips_failed_query(capsys):
    def route(url, params):
        raise RuntimeError("timeout")

    assert list(fetch_remotive(make_client(route), SUMMARY, {})) == []
    assert "[REMOTIVE]" in capsys.readouterr().out


# ── _canada_eligible ──────────────────────────────────────────────────────────


def test_canada_eligible_rules():
    assert _canada_eligible("") is True  # unknown → don't over-filter
    assert _canada_eligible("Anywhere in the World") is True
    assert _canada_eligible("Canada, United States") is True
    assert _canada_eligible("North America Only") is True
    assert _canada_eligible("USA Only") is False
    assert _canada_eligible("Europe Only") is False
    assert _canada_eligible("United States") is False


def test_rfc822_to_date():
    assert _rfc822_to_date("Sun, 17 May 2026 20:30:53 +0000") == "2026-05-17"
    assert _rfc822_to_date("") is None
    assert _rfc822_to_date("not a date") is None


# ── fetch_himalayas ───────────────────────────────────────────────────────────


def test_fetch_himalayas_keeps_canada_eligible_and_shapes():
    payload = {
        "jobs": [
            {
                "title": "Staff Engineer",
                "companyName": "Acme",
                "applicationLink": "https://himalayas.app/companies/acme/jobs/staff",
                "guid": "https://himalayas.app/x",
                "pubDate": 1780630888,
                "locationRestrictions": ["Canada", "United States"],
                "description": "<p>Remote role</p>",
            },
            {
                "title": "US Only Role",
                "companyName": "Beta",
                "applicationLink": "u2",
                "pubDate": 1780630888,
                "locationRestrictions": ["United States"],
                "description": "x",
            },
        ]
    }
    cfg = {"pages": 1}
    jobs = list(fetch_himalayas(make_client(lambda url, params: FakeResp(payload)), SUMMARY, cfg))
    assert [j["title"] for j in jobs] == ["Staff Engineer"]
    assert jobs[0]["company"] == "Acme"
    assert jobs[0]["url"] == "https://himalayas.app/companies/acme/jobs/staff"
    assert jobs[0]["location"] == "Remote — Canada, United States"
    assert jobs[0]["description"] == "Remote role"
    assert jobs[0]["post_date"] == _epoch_ms_to_date(1780630888 * 1000)


def test_fetch_himalayas_handles_fetch_failure(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_himalayas(make_client(route), SUMMARY, {"pages": 1})) == []
    assert "[HIMALAYAS]" in capsys.readouterr().out


# ── fetch_wwr ─────────────────────────────────────────────────────────────────

WWR_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Acme Corp: Staff Engineer</title>
    <region>Anywhere in the World</region>
    <link>https://weworkremotely.com/remote-jobs/acme-staff</link>
    <pubDate>Sun, 17 May 2026 20:30:53 +0000</pubDate>
    <description>&lt;p&gt;Remote senior role&lt;/p&gt;</description>
  </item>
  <item>
    <title>Beta Inc: Local Dev</title>
    <region>USA Only</region>
    <link>u2</link>
    <pubDate>Sun, 17 May 2026 20:30:53 +0000</pubDate>
    <description>x</description>
  </item>
</channel></rss>"""


def test_fetch_wwr_splits_title_filters_region_and_shapes():
    cfg = {"categories": ["remote-programming-jobs"]}
    jobs = list(
        fetch_wwr(make_client(lambda url, params: FakeResp(None, text=WWR_RSS_XML)), SUMMARY, cfg)
    )
    assert [j["title"] for j in jobs] == ["Staff Engineer"]
    assert jobs[0]["company"] == "Acme Corp"
    assert jobs[0]["url"] == "https://weworkremotely.com/remote-jobs/acme-staff"
    assert jobs[0]["post_date"] == "2026-05-17"
    assert jobs[0]["location"] == "Remote — Anywhere in the World"
    assert jobs[0]["description"] == "Remote senior role"


def test_fetch_wwr_skips_failed_category(capsys):
    def route(url, params):
        raise RuntimeError("boom")

    assert list(fetch_wwr(make_client(route), SUMMARY, {"categories": ["x"]})) == []
    assert "[WWR]" in capsys.readouterr().out
