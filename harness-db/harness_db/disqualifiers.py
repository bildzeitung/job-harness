"""Load and apply the harness's hard disqualifiers.

`disqualifiers.yaml` is the single, user-editable source of truth for the
pipeline's hard exclusions. It holds two independent sections:

* ``prefilter`` — keyword rules applied as EARLY as possible (at search time by
  every source, and again by ``job-preparer`` before scoring) to drop noise
  before it costs anything. This is the one exclusion layer; searchers no longer
  carry their own hard-coded keyword lists.
* ``scoring_modifiers`` — negative score modifiers the scorer LLM applies during
  scoring.

Promoted here (alongside :mod:`harness_db.config` and :mod:`harness_db.profile`)
so every pipeline module — ``api_search``, ``scoring_module``, and any future
consumer — shares one loader, one path-resolution rule, and one prefilter
implementation.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from harness_db.config import get_job_data_root

__all__ = ["load_disqualifiers", "load_prefilter", "prefilter_disqualifies"]

_FILENAME = "disqualifiers.yaml"
_DEFAULT_TEMPLATE = Path(__file__).with_name("disqualifiers.default.yaml")


def load_disqualifiers() -> dict[str, Any]:
    """Read ``$JOB_DATA_ROOT/disqualifiers.yaml``.

    Seeds the live copy from the bundled default on first run so the file is
    always present and editable in one place.
    """
    live = get_job_data_root() / _FILENAME
    if not live.exists():
        live.write_text(_DEFAULT_TEMPLATE.read_text())
    with open(live) as f:
        return yaml.safe_load(f) or {}


def load_prefilter() -> dict[str, Any]:
    """Return just the ``prefilter`` section of the disqualifiers config."""
    return load_disqualifiers().get("prefilter", {}) or {}


@lru_cache(maxsize=None)
def _phrase_regex(phrase: str) -> re.Pattern[str]:
    """Compile a disqualifier phrase to a case-insensitive, word-bounded regex.

    Plain substring matching over-fired in two reported ways, both fixed here:

    * Word boundaries are added only at edges that are alphanumeric, so a token
      like ``defi`` matches the standalone word (and ``DeFi``) but no longer the
      ``defi`` inside ``defines``/``defining``. A phrase that already starts or
      ends in punctuation (e.g. ``remote (US)``) gets no boundary on that side,
      so it keeps matching as before.
    * A trailing ``(?!/canada)`` lookahead on alphanumeric-ending phrases means a
      geography keyword glued onto ``/canada`` does not fire — ``remote - us``
      stops matching the Canada-eligible ``remote - us/canada`` while still
      matching ``remote - us`` on its own. This is narrow on purpose: slash
      compounds like ``blockchain/web3`` (anything other than ``/canada``) still
      match, so crypto exclusions are unaffected.
    """
    prefix = r"\b" if phrase[:1].isalnum() else ""
    suffix = r"\b(?!/canada)" if phrase[-1:].isalnum() else ""
    return re.compile(prefix + re.escape(phrase) + suffix, re.IGNORECASE)


def prefilter_disqualifies(title: str, text: str, prefilter: dict[str, Any]) -> bool:
    """True if a posting matches any hard prefilter rule (case-insensitive).

    Implements the canonical semantics shared by every source and by
    ``job-preparer``. Matching is word-bounded (see :func:`_phrase_regex`) so
    keywords match whole words, not substrings inside larger words.

    * ``description_phrases`` — any phrase appears in the title or description.
    * ``title_terms`` — any term appears in the title.
    * ``title_terms_unless_senior`` — any term appears in the title, UNLESS the
      title also contains a ``seniority_exceptions`` term (e.g. "senior",
      "staff", "principal" — seniority qualifiers, not contradictions).
    """
    combined = f"{title} {text}"

    for phrase in prefilter.get("description_phrases", []):
        if _phrase_regex(phrase).search(combined):
            return True

    for term in prefilter.get("title_terms", []):
        if _phrase_regex(term).search(title):
            return True

    seniority_exceptions = prefilter.get("seniority_exceptions", [])
    has_seniority = any(_phrase_regex(s).search(title) for s in seniority_exceptions)
    if not has_seniority:
        for term in prefilter.get("title_terms_unless_senior", []):
            if _phrase_regex(term).search(title):
                return True

    return False
