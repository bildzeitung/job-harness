"""Tests for harness_db.report aggregation and rendering."""

from __future__ import annotations

import json

from harness_db.models import Posting
from harness_db.report import (
    render_report,
    report_data,
    score_histogram,
    status_summary,
    top_postings,
)


def _scored(
    url: str,
    score: int,
    *,
    applicants: int | None = None,
    scored_date: str = "2026-05-29T00:00:00Z",
    company: str = "Co",
    title: str = "Role",
) -> Posting:
    return Posting(
        url=url,
        company=company,
        title=title,
        status="scored",
        final_score=score,
        applicant_count=applicants,
        scored_date=scored_date,
    )


def test_status_summary_counts_and_orders_by_state():
    postings = [
        Posting(url="a", status="new"),
        Posting(url="b", status="new"),
        Posting(url="c", status="prepared"),
        Posting(url="d", status=None),  # treated as "new"
    ]
    assert status_summary(postings) == [("prepared", 1), ("new", 3)]


def test_status_summary_unknown_status_sorts_last():
    postings = [Posting(url="a", status="mystery"), Posting(url="b", status="scored")]
    assert status_summary(postings) == [("scored", 1), ("mystery", 1)]


def test_score_histogram_buckets_high_first_and_skips_unscored():
    postings = [
        _scored("a", 82),
        _scored("b", 88),
        _scored("c", 75),
        Posting(url="d", status="new", final_score=None),
    ]
    assert score_histogram(postings) == [("80-89", 2), ("70-79", 1)]


def test_top_postings_filters_by_min_score_and_status():
    postings = [
        _scored("hit", 90),
        _scored("low", 60),
        Posting(url="new", status="new", final_score=99),
    ]
    result = top_postings(postings, min_score=75)
    assert [p.url for p in result] == ["hit"]


def test_top_postings_orders_by_score_then_fewest_applicants():
    postings = [
        _scored("mid", 80, applicants=5),
        _scored("top-many", 90, applicants=100),
        _scored("top-few", 90, applicants=3),
        _scored("top-unknown", 90, applicants=None),
    ]
    result = top_postings(postings, min_score=75)
    assert [p.url for p in result] == ["top-few", "top-many", "top-unknown", "mid"]


def test_top_postings_respects_scored_on_prefix_and_limit():
    postings = [
        _scored("today1", 90, scored_date="2026-05-29T10:00:00Z"),
        _scored("today2", 85, scored_date="2026-05-29T11:00:00Z"),
        _scored("yesterday", 95, scored_date="2026-05-28T09:00:00Z"),
    ]
    result = top_postings(postings, min_score=75, limit=1, scored_on="2026-05-29")
    assert [p.url for p in result] == ["today1"]


def test_render_report_includes_all_sections():
    postings = [_scored("a", 90, applicants=4), Posting(url="b", status="new")]
    out = render_report(postings, min_score=75, top=5)
    assert "Postings: 2" in out
    assert "By status" in out
    assert "Score distribution (scored only)" in out
    assert "Top 5 (score >= 75)" in out
    assert "Co" in out


def test_report_data_top_and_below_min_counts():
    postings = [
        _scored("hit", 90, applicants=4, company="Acme", title="Principal Engineer"),
        _scored("low", 60),
        Posting(url="new", status="new"),
    ]
    data = report_data(postings, min_score=75, top=5)
    assert data["total"] == 3
    assert data["min_score"] == 75
    assert data["scored_total"] == 2
    assert data["scored_below_min"] == 1
    assert [row["url"] for row in data["top"]] == ["hit"]
    top = data["top"][0]
    assert top["company"] == "Acme"
    assert top["title"] == "Principal Engineer"
    assert top["final_score"] == 90
    assert top["applicant_count"] == 4
    # job_description_text is intentionally excluded (large, re-fetched on demand).
    assert "job_description_text" not in top


def test_report_data_scored_on_scopes_counts_and_top():
    postings = [
        _scored("today", 90, scored_date="2026-05-29T10:00:00Z"),
        _scored("today-low", 60, scored_date="2026-05-29T11:00:00Z"),
        _scored("yesterday", 95, scored_date="2026-05-28T09:00:00Z"),
    ]
    data = report_data(postings, min_score=75, top=5, scored_on="2026-05-29")
    assert data["scored_total"] == 2
    assert data["scored_below_min"] == 1
    assert [row["url"] for row in data["top"]] == ["today"]


def test_report_data_top_is_json_serializable():
    data = report_data([_scored("a", 90)], min_score=75, top=5)
    json.dumps(data)  # must not raise
