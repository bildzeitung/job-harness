"""Tests for api_search.filters (positive match filters only).

Hard exclusions are driven by the disqualifiers prefilter and are tested in
``harness_db.tests.test_disqualifiers``.
"""

import pytest

from api_search.filters import is_remote, is_senior

SENIORITY = ["principal", "staff", "cloud architect", "senior staff"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Fully remote role", True),
        ("Remote-first company", True),
        ("On-site in Toronto", False),
        ("Hybrid work arrangement", False),
    ],
)
def test_is_remote(text, expected):
    assert is_remote(text) is expected


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Principal Software Engineer", True),
        ("Staff Engineer", True),
        ("Cloud Architect", True),
        ("Senior Staff Engineer", True),
        ("Software Developer II", False),
        ("Junior Engineer", False),
    ],
)
def test_is_senior(title, expected):
    assert is_senior(title, SENIORITY) is expected
