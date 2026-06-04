"""Read/write helpers for the ``postings_vec`` sqlite-vec table.

The extension is loaded and the table created by ``harness_db.models.make_engine``
(best-effort, in the connection event), so every connection from that engine can
query vectors. These helpers take a raw DBAPI cursor because sqlite-vec's
``MATCH`` / ``k =`` KNN syntax is driver-level SQL, not ORM-expressible.

Distances are **cosine** (table created with ``distance_metric=cosine``): 0.0 is
identical, ~1.0 is unrelated, 2.0 is opposite.
"""

from __future__ import annotations

from sqlalchemy import Engine

from harness_db.embeddings import embed

__all__ = [
    "DUPLICATE_DISTANCE",
    "upsert_vector",
    "delete_vector",
    "nearest",
    "find_duplicate",
]

# Cosine distance at/below which two postings are treated as the same job. Tuned
# to catch cross-platform reposts (same JD, different URL and surrounding
# boilerplate) without merging merely-similar roles. Widen toward ~0.12 if reposts
# slip through; tighten toward ~0.05 if distinct roles get merged.
DUPLICATE_DISTANCE = 0.08


def upsert_vector(engine: Engine, url: str, text: str) -> None:
    """Embed ``text`` and store/replace the vector keyed by ``url``."""
    emb = embed(text)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO postings_vec(url, embedding) VALUES (?, ?)",
            (url, emb),
        )
        cur.close()
        raw.commit()
    finally:
        raw.close()


def delete_vector(engine: Engine, url: str) -> None:
    """Drop the vector for ``url`` (call when a posting is purged)."""
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("DELETE FROM postings_vec WHERE url = ?", (url,))
        cur.close()
        raw.commit()
    finally:
        raw.close()


def nearest(
    engine: Engine, text: str, k: int = 5, exclude_url: str | None = None
) -> list[tuple[str, float]]:
    """Return up to ``k`` ``(url, cosine_distance)`` pairs nearest to ``text``.

    Closest first. ``exclude_url`` drops a self-match (e.g. when ranking jobs
    "more like this one"); we over-fetch by one so the exclusion never shrinks
    the result below ``k``.
    """
    emb = embed(text)
    limit = k + (1 if exclude_url else 0)
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute(
            "SELECT url, distance FROM postings_vec "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (emb, limit),
        )
        rows = cur.fetchall()
        cur.close()
    finally:
        raw.close()
    hits = [(url, dist) for url, dist in rows if url != exclude_url]
    return hits[:k]


def find_duplicate(
    engine: Engine,
    text: str,
    *,
    exclude_url: str | None = None,
    threshold: float = DUPLICATE_DISTANCE,
) -> tuple[str, float] | None:
    """Return ``(url, distance)`` of an existing near-duplicate posting, or None.

    Use at ingest time (consolidator) to skip inserting a repost, or in the
    scorer to copy an already-computed score instead of re-calling the LLM.
    """
    hits = nearest(engine, text, k=1, exclude_url=exclude_url)
    if hits and hits[0][1] <= threshold:
        return hits[0]
    return None
