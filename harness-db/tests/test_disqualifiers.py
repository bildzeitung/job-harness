"""Tests for harness_db.disqualifiers: loading/seeding and the prefilter predicate."""

from __future__ import annotations

import pytest

from harness_db import disqualifiers

PREFILTER = {
    "description_phrases": ["us work authorization", "must relocate"],
    "title_terms": [" intern ", "internship"],
    "title_terms_unless_senior": ["entry-level", " junior "],
    "seniority_exceptions": ["senior", "staff", "principal"],
}


@pytest.mark.parametrize(
    "title,text,expected",
    [
        # description_phrases match in description
        ("Principal Engineer", "Must have US work authorization", True),
        ("Staff Engineer", "Candidate must relocate to Austin", True),
        # description_phrases match in title
        ("Intern - must relocate", "", True),
        # title_terms match in title
        ("Software internship program", "", True),
        ("Engineering Intern (Remote)", "", True),  # " intern " padded match
        # title_terms_unless_senior: plain match disqualifies (" junior " is padded
        # in the term, so it matches mid-title but not a leading "Junior...")
        ("Entry-level Developer", "remote", True),
        ("Lead Junior Developer", "remote", True),
        # ...unless a seniority exception is present in the title
        ("Senior Engineer (no entry-level fluff)", "", False),
        # clean senior roles pass
        ("Principal Software Engineer", "Fully remote, open to Canada", False),
        ("Staff Platform Engineer", "Remote-first", False),
    ],
)
def test_prefilter_disqualifies(title, text, expected):
    assert disqualifiers.prefilter_disqualifies(title, text, PREFILTER) is expected


def test_prefilter_disqualifies_is_case_insensitive():
    assert disqualifiers.prefilter_disqualifies("Lead", "US WORK AUTHORIZATION required", PREFILTER)


@pytest.mark.parametrize(
    "title,text,expected",
    [
        ("Lead", "Must have US work authorization", "description_phrases: us work authorization"),
        ("Software internship program", "", "title_terms: internship"),
        ("Entry-level Developer", "remote", "title_terms_unless_senior: entry-level"),
        # seniority exception suppresses the unless_senior match
        ("Senior Engineer (no entry-level fluff)", "", None),
        ("Principal Software Engineer", "Fully remote", None),
    ],
)
def test_prefilter_match_names_the_firing_rule(title, text, expected):
    assert disqualifiers.prefilter_match(title, text, PREFILTER) == expected


def test_prefilter_match_agrees_with_disqualifies():
    cases = [
        ("Principal Engineer", "Must have US work authorization"),
        ("Engineering Intern (Remote)", ""),
        ("Staff Platform Engineer", "Remote-first"),
    ]
    for title, text in cases:
        assert (disqualifiers.prefilter_match(title, text, PREFILTER) is not None) is (
            disqualifiers.prefilter_disqualifies(title, text, PREFILTER)
        )


# Word-boundary matching: keywords match whole words, not substrings inside
# larger words, and a geography keyword glued onto "/canada" does not fire.
WORD_BOUNDARY_PREFILTER = {
    "description_phrases": ["defi", "remote - us", "blockchain", "remote (US)"],
}


@pytest.mark.parametrize(
    "title,text,expected",
    [
        # "defi" matches the standalone crypto term and "DeFi"...
        ("Engineer", "We build a DeFi protocol", True),
        ("Engineer", "smart contracts for defi", True),
        # ...but no longer the "defi" inside "defines"/"defining" (the reported
        # false positive: a PointClickCare / Best Buy posting).
        ("Principal Engineer AI", "The architect defines and refines APIs", False),
        ("Enterprise Architect", "defining the platform roadmap", False),
        # "remote - us" matches a US-only posting on its own...
        ("Staff Engineer", "This role is remote - US based", True),
        ("Staff Engineer", "Remote - US", True),
        # ...but not the Canada-eligible "remote - us/canada" (the reported
        # Docker Staff Backend Engineer false positive).
        ("Staff Backend Engineer", "Location: Remote - US/Canada", False),
        # the "/canada" exception is narrow — other slash compounds still match,
        # so crypto exclusions are unaffected.
        ("Engineer", "We are a blockchain/web3 company", True),
    ],
)
def test_prefilter_word_boundaries(title, text, expected):
    assert disqualifiers.prefilter_disqualifies(title, text, WORD_BOUNDARY_PREFILTER) is expected


def test_prefilter_disqualifies_empty_prefilter_passes_everything():
    assert disqualifiers.prefilter_disqualifies("Junior Intern", "us only", {}) is False


def test_load_disqualifiers_seeds_from_default_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    live = tmp_path / "disqualifiers.yaml"
    assert not live.exists()

    config = disqualifiers.load_disqualifiers()

    assert live.exists()  # seeded from the packaged default
    assert "prefilter" in config
    assert "scoring_modifiers" in config


def test_load_disqualifiers_reads_existing_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setenv("JOB_DATA_ROOT", str(tmp_path))
    (tmp_path / "disqualifiers.yaml").write_text("prefilter:\n  title_terms:\n    - widget\n")

    assert disqualifiers.load_prefilter() == {"title_terms": ["widget"]}
