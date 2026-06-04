"""One-off: embed existing postings into the ``postings_vec`` table.

Run after installing the ``semantic`` extra and pulling the Ollama model::

    ollama pull qwen3-embedding:0.6b
    python -m harness_db.backfill_embeddings

Idempotent — re-running re-embeds (``INSERT OR REPLACE``), so this is also how
you rebuild the index after switching ``HARNESS_EMBED_MODEL``.
"""

from __future__ import annotations

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_db.config import get_db_path
from harness_db.models import Posting, make_engine
from harness_db.vectors import upsert_vector


def _text_for(p: Posting) -> str:
    """Prefer the full JD, fall back to the summary, then the title."""
    return (p.job_description_text or p.description_summary or p.title or "").strip()


def main() -> int:
    engine = make_engine(get_db_path())
    with Session(engine) as session:
        postings = list(session.scalars(select(Posting)))

    done = 0
    for p in postings:
        text = _text_for(p)
        if not text:
            continue
        try:
            upsert_vector(engine, p.url, text)
            done += 1
            print(f"[EMBED] {p.display_name}", flush=True)
        except Exception as exc:  # keep going; one bad row shouldn't abort the run
            print(f"[ERROR] {p.url}: {exc}", file=sys.stderr, flush=True)

    print(f"[DONE] embedded {done}/{len(postings)} postings", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
