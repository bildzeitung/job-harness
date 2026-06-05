"""One-off: embed existing postings into the ``postings_vec`` table.

Run after installing the harness and pulling the Ollama model::

    ollama pull qwen3-embedding:0.6b
    python -m harness_db.backfill_embeddings              # (re-)embed everything
    python -m harness_db.backfill_embeddings --missing-only  # only postings not yet indexed

A full run re-embeds every posting (``INSERT OR REPLACE``), so it doubles as the
rebuild after switching ``HARNESS_EMBED_MODEL``. ``--missing-only`` skips postings
already in ``postings_vec`` — use it to resume an interrupted run or to catch up
new rows cheaply.
"""

from __future__ import annotations

import sys

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from harness_db.config import get_db_path
from harness_db.models import Posting, make_engine
from harness_db.vectors import upsert_vector


def _text_for(p: Posting) -> str:
    """Prefer the full JD, fall back to the summary, then the title."""
    return (p.job_description_text or p.description_summary or p.title or "").strip()


def _indexed_urls(engine) -> set[str]:
    """URLs already present in postings_vec."""
    raw = engine.raw_connection()
    try:
        cur = raw.cursor()
        cur.execute("SELECT url FROM postings_vec")
        return {row[0] for row in cur.fetchall()}
    finally:
        raw.close()


def run(missing_only: bool = False) -> int:
    engine = make_engine(get_db_path())
    with Session(engine) as session:
        postings = list(session.scalars(select(Posting)))

    already = _indexed_urls(engine) if missing_only else set()

    done = 0
    skipped = 0
    for p in postings:
        if missing_only and p.url in already:
            skipped += 1
            continue
        text = _text_for(p)
        if not text:
            continue
        try:
            upsert_vector(engine, p.url, text)
            done += 1
            print(f"[EMBED] {p.display_name}", flush=True)
        except Exception as exc:  # keep going; one bad row shouldn't abort the run
            print(f"[ERROR] {p.url}: {exc}", file=sys.stderr, flush=True)

    tail = f" (skipped {skipped} already-indexed)" if missing_only else ""
    print(f"[DONE] embedded {done}/{len(postings)} postings{tail}", flush=True)
    return 0


app = typer.Typer(help="Backfill posting embeddings into postings_vec.")


@app.command()
def main(
    missing_only: bool = typer.Option(
        False,
        "--missing-only",
        help="Skip postings already present in postings_vec (resume / incremental catch-up).",
    ),
) -> None:
    raise typer.Exit(run(missing_only=missing_only))


if __name__ == "__main__":
    app()
