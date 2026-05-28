"""Tests for api_search.filters."""

import pytest

from api_search.filters import is_canada_eligible, is_junior, is_remote, is_senior

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


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Junior Software Engineer", True),
        ("Intern, Platform Team", True),
        ("Entry level developer", True),
        ("Entry-Level Engineer", True),
        ("Senior Engineer", False),
        ("Principal Architect", False),
    ],
)
def test_is_junior(title, expected):
    assert is_junior(title) is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Open to Canadian candidates", True),
        ("Remote, worldwide", True),
        ("US only — must have US work authorization", False),
        ("US citizens only", False),
        ("Must be located in US", False),
    ],
)
def test_is_canada_eligible(text, expected):
    assert is_canada_eligible(text) is expected
