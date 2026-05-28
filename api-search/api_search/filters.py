"""Shared posting filters — applied uniformly to every source's results."""

from __future__ import annotations

JUNIOR_KEYWORDS = ["junior", "intern", "entry level", "entry-level"]

EXCLUDE_PHRASES = ["us only", "us citizens only", "must be located in us"]


def is_remote(text: str) -> bool:
    return "remote" in text.lower()


def is_senior(title: str, seniority_keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in seniority_keywords)


def is_junior(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in JUNIOR_KEYWORDS)


def is_canada_eligible(text: str) -> bool:
    t = text.lower()
    return not any(phrase in t for phrase in EXCLUDE_PHRASES)
