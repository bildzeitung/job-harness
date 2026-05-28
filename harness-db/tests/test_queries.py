"""Tests for harness_db.queries sort ordering and DB round-trips."""

from __future__ import annotations

import pytest

from harness_db.models import Base, Posting, make_engine
from harness_db.queries import _sort_postings, get_postings, update_status


def _posting(url: str, title: str, first_seen: str, status: str) -> Posting:
    return Posting(url=url, title=title, first_seen=first_seen, status=status)


def test_sort_by_state_orders_by_priority_then_date_then_title():
    postings = [
        _posting("u-new", "Beta", "2026-05-01", "new"),
        _posting("u-prepared", "Zeta", "2026-04-01", "prepared"),
        _posting("u-applied", "Alpha", "2026-05-20", "applied"),
    ]
    result = _sort_postings(list(postings), "state")
    assert [p.url for p in result] == ["u-prepared", "u-new", "u-applied"]


def test_sort_by_state_unknown_status_sorts_last():
    postings = [
        _posting("u-weird", "Aaa", "2026-05-01", "mystery"),
        _posting("u-new", "Bbb", "2026-05-01", "new"),
    ]
    result = _sort_postings(list(postings), "state")
    assert [p.url for p in result] == ["u-new", "u-weird"]


def test_sort_by_date_is_newest_first():
    postings = [
        _posting("u-old", "Aaa", "2026-01-01", "new"),
        _posting("u-new", "Bbb", "2026-05-01", "new"),
    ]
    result = _sort_postings(list(postings), "date")
    assert [p.url for p in result] == ["u-new", "u-old"]


def test_sort_by_title_is_alphabetical():
    postings = [
        _posting("u-z", "Zebra", "2026-05-01", "new"),
        _posting("u-a", "Apple", "2026-01-01", "new"),
    ]
    result = _sort_postings(list(postings), "title")
    assert [p.url for p in result] == ["u-a", "u-z"]


@pytest.fixture
def engine(tmp_path):
    eng = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(eng)
    return eng


def test_get_postings_and_update_status_round_trip(engine):
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        session.add(_posting("u1", "Role", "2026-05-01", "new"))
        session.commit()

    update_status(engine, "u1", "selected")

    postings = get_postings(engine)
    assert len(postings) == 1
    assert postings[0].status == "selected"
