"""Tests for email_parser.parser"""


from email_parser.parser import (
    filter_by_seniority,
    parse,
)

# ── helpers ──────────────────────────────────────────────────────────────────


def _card(job_id: str, title: str, company: str, location: str = "Toronto, ON · Remote") -> str:
    """Minimal HTML job card matching LinkedIn alert email structure."""
    return (
        f'<a href="https://www.linkedin.com/comm/jobs/view/{job_id}?trackingId=abc123">'
        f"{title}</a>"
        f"<span>{company} · {location}</span>"
    )


# ── parse — anchor-based extraction ──────────────────────────────────────────


def test_parse_extracts_title_from_anchor():
    jobs = parse(_card("111", "Senior Software Engineer", "Acme Corp"))
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Software Engineer"


def test_parse_extracts_company_from_span():
    jobs = parse(_card("111", "Senior Software Engineer", "Acme Corp"))
    assert jobs[0]["company"] == "Acme Corp"


def test_parse_canonical_url_strips_query_params():
    jobs = parse(_card("999", "Principal Engineer", "Beta Ltd"))
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/999"


def test_parse_deduplicates_same_job_id():
    html = _card("111", "Senior Engineer", "Co A") + _card("111", "Senior Engineer", "Co A")
    assert len(parse(html)) == 1


def test_parse_multiple_cards():
    html = _card("1", "Senior Software Engineer, Cloud", "Redpanda Data") + _card(
        "2", "Principal Platform Engineer", "StreamSets"
    )
    jobs = parse(html)
    assert len(jobs) == 2
    urls = {j["url"] for j in jobs}
    assert "https://www.linkedin.com/jobs/view/1" in urls
    assert "https://www.linkedin.com/jobs/view/2" in urls


def test_parse_strips_html_entities_from_title():
    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/5555">'
        "Senior Software Engineer &mdash; AI &amp; Platform</a>"
        "<span>Acme · Remote</span>"
    )
    jobs = parse(html)
    assert "AI" in jobs[0]["title"]
    # &mdash; → —, &amp; → &  (entities decoded, raw entity strings gone)
    assert "&mdash;" not in jobs[0]["title"]
    assert "&amp;" not in jobs[0]["title"]
    assert "—" in jobs[0]["title"]
    assert "&" in jobs[0]["title"]


def test_parse_strips_inner_tags_from_title():
    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/5556">'
        "<strong>Senior</strong> Software Engineer</a>"
        "<p>Acme Corp · Remote</p>"
    )
    jobs = parse(html)
    assert jobs[0]["title"] == "Senior Software Engineer"


def test_parse_skips_view_job_anchors():
    # "View job" link for same ID should not count as the title
    html = (
        '<a href="https://www.linkedin.com/comm/jobs/view/888">View job</a>'
        '<a href="https://www.linkedin.com/comm/jobs/view/777">Senior Engineer</a>'
        "<span>Acme · Remote</span>"
    )
    jobs = parse(html)
    titles = {j["title"] for j in jobs}
    assert "Senior Engineer" in titles
    assert "View job" not in titles


def test_parse_returns_empty_for_no_jobs():
    assert parse("<html><body>No jobs here</body></html>") == []


# ── parse — bare-URL fallback ─────────────────────────────────────────────────


def test_parse_fallback_bare_url():
    # URL appears in plain text, not in an <a> tag
    html = "Senior Software Engineer at BigCo https://www.linkedin.com/jobs/view/77777"
    jobs = parse(html)
    assert len(jobs) == 1
    assert jobs[0]["url"] == "https://www.linkedin.com/jobs/view/77777"


def test_parse_fallback_extracts_title_from_window():
    html = (
        "Some text Principal Cloud Architect · Infra Corp "
        "https://www.linkedin.com/jobs/view/22222 more text"
    )
    jobs = parse(html)
    assert "Principal" in jobs[0]["title"]


def test_parse_anchor_takes_priority_over_bare_url():
    # Same job ID present both as an anchor AND as a bare URL downstream
    html = (
        _card("333", "Senior Engineer", "GoodCo")
        + " and also https://www.linkedin.com/jobs/view/333 elsewhere"
    )
    jobs = parse(html)
    # Should only appear once; the anchor-based entry wins
    assert len(jobs) == 1
    assert jobs[0]["title"] == "Senior Engineer"


# ── parse — company extraction edge cases ────────────────────────────────────


def test_parse_company_with_ampersand():
    jobs = parse(_card("444", "Staff Engineer", "AT&T"))
    assert jobs[0]["company"] == "AT&T"


def test_parse_company_with_exclamation():
    jobs = parse(_card("445", "Staff Engineer", "Aha!"))
    assert jobs[0]["company"] == "Aha!"


def test_parse_company_not_bleed_into_next_card():
    html = _card("101", "Sr. Platform Engineer", "Aha!") + _card(
        "102", "Software Engineer I", "Startup Co"
    )
    jobs = parse(html)
    by_id = {j["url"].split("/")[-1]: j for j in jobs}
    assert by_id["101"]["company"] == "Aha!"
    assert by_id["102"]["company"] == "Startup Co"


def test_parse_company_unknown_when_no_context():
    # Anchor text is present but nothing follows it
    html = '<a href="https://www.linkedin.com/comm/jobs/view/9001">Senior Engineer</a>'
    jobs = parse(html)
    assert jobs[0]["company"] == "Unknown Company"


# ── filter_by_seniority ───────────────────────────────────────────────────────

_MIX = [
    {"title": "Senior Software Engineer", "company": "A", "url": "u1"},
    {"title": "Junior Developer", "company": "B", "url": "u2"},
    {"title": "Principal Architect", "company": "C", "url": "u3"},
    {"title": "Staff Engineer", "company": "D", "url": "u4"},
    {"title": "Sr. Platform Engineer", "company": "E", "url": "u5"},
    {"title": "Lead Data Engineer", "company": "F", "url": "u6"},
    {"title": "Software Developer II", "company": "G", "url": "u7"},
    {"title": "VP of Engineering", "company": "H", "url": "u8"},
]


def test_filter_keeps_senior_variants():
    result = filter_by_seniority(_MIX)
    titles = {j["title"] for j in result}
    assert "Senior Software Engineer" in titles
    assert "Principal Architect" in titles
    assert "Staff Engineer" in titles
    assert "Sr. Platform Engineer" in titles
    assert "Lead Data Engineer" in titles
    assert "VP of Engineering" in titles


def test_filter_removes_non_senior():
    result = filter_by_seniority(_MIX)
    titles = {j["title"] for j in result}
    assert "Junior Developer" not in titles
    assert "Software Developer II" not in titles


def test_filter_custom_keywords():
    result = filter_by_seniority(_MIX, keywords=["junior"])
    assert len(result) == 1
    assert result[0]["title"] == "Junior Developer"


def test_filter_empty_input():
    assert filter_by_seniority([]) == []


def test_filter_preserves_order():
    jobs = [
        {"title": "Senior Engineer", "company": "A", "url": "u1"},
        {"title": "Staff Engineer", "company": "B", "url": "u2"},
    ]
    result = filter_by_seniority(jobs)
    assert [j["url"] for j in result] == ["u1", "u2"]


# ── integration: parse + filter ───────────────────────────────────────────────


def test_integration_real_like_email():
    html = (
        _card("4416736073", "Senior Software Engineer, Cloud", "Redpanda Data")
        + _card("4418121425", "Senior Software Developer (Remote)", "Hire Feed")
        + _card("4417797074", "Sr. Platform Engineer", "Aha!")
        + _card("9999999999", "Software Engineer I", "StartupCo")  # should be filtered
    )
    jobs = filter_by_seniority(parse(html))
    titles = {j["title"] for j in jobs}
    assert "Senior Software Engineer, Cloud" in titles
    assert "Senior Software Developer (Remote)" in titles
    assert "Sr. Platform Engineer" in titles
    assert "Software Engineer I" not in titles
    assert len(jobs) == 3
