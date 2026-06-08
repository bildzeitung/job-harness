"""Command-line entry point for harness DB operations.

``harness-db report`` prints (or, with ``--json``, emits) the status summary,
score distribution, and top-N fit table for the canonical DB (resolved via
:func:`harness_db.config.get_db_path`, overridable with ``--db``). ``harness-db
candidate`` prints a field from ``candidate-summary.json`` so agents read the
shared profile through one loader instead of inline JSON parsing. Both live on a
single :class:`typer.Typer` app so future helpers share the same DB-resolution
and error handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import typer

from harness_db.config import get_db_path
from harness_db.disqualifiers import load_prefilter, prefilter_disqualifies
from harness_db.models import Posting, make_engine
from harness_db.profile import load_candidate_summary
from harness_db.queries import get_postings, update_status
from harness_db.report import render_report, report_data

app = typer.Typer(help="Job-harness DB tools.", no_args_is_help=True)


def _posting_dict(p: Posting, full: bool) -> dict:
    """Project a Posting row to a JSON-friendly dict for the `postings` command."""
    d = {
        "url": p.url,
        "title": p.title,
        "company": p.company,
        "platform": p.platform,
        "status": p.status,
        "post_date": p.post_date,
        "applicant_count": p.applicant_count,
        "base_score": p.base_score,
        "final_score": p.final_score,
        "scored_date": p.scored_date,
        "description_summary": p.description_summary,
    }
    if full:
        d["job_description_text"] = p.job_description_text
    return d


def _resolve_db(db: Optional[Path]) -> Path:
    try:
        db_path = db or get_db_path()
    except (RuntimeError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    if not db_path.exists():
        typer.echo(f"Database not found: {db_path}", err=True)
        raise typer.Exit(1)
    return db_path


@app.command()
def report(
    db: Optional[Path] = typer.Option(None, "--db", help="Override the SQLite DB path."),
    min_score: int = typer.Option(75, "--min-score", help="Minimum score for top list."),
    top: int = typer.Option(15, "--top", help="How many top postings to list."),
    scored_on: Optional[str] = typer.Option(
        None,
        "--scored-on",
        help="Limit top list to postings scored on this date prefix, e.g. 2026-05-29.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit structured JSON (ranked rows + counts) instead of the text table.",
    ),
) -> None:
    """Status summary, score distribution, and top fits."""
    engine = make_engine(_resolve_db(db))
    postings = get_postings(engine)
    if json_output:
        typer.echo(
            json.dumps(
                report_data(postings, min_score=min_score, top=top, scored_on=scored_on),
                indent=2,
            )
        )
    else:
        typer.echo(render_report(postings, min_score=min_score, top=top, scored_on=scored_on))


@app.command()
def candidate(
    field: str = typer.Option(
        "name",
        "--field",
        help="Which candidate-summary.json field to print (default: name).",
    ),
    filename_safe: bool = typer.Option(
        False,
        "--filename-safe",
        help="Replace spaces with underscores (e.g. for resume PDF filenames).",
    ),
) -> None:
    """Print a field from candidate-summary.json (default: name)."""
    try:
        summary = load_candidate_summary()
    except (RuntimeError, FileNotFoundError) as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    value = summary.get(field)
    if value is None:
        typer.echo(f"Field {field!r} not in candidate-summary.json", err=True)
        raise typer.Exit(1)
    value = str(value)
    if filename_safe:
        value = value.replace(" ", "_")
    typer.echo(value)


@app.command()
def postings(
    db: Optional[Path] = typer.Option(None, "--db", help="Override the SQLite DB path."),
    status: Optional[List[str]] = typer.Option(
        None, "--status", help="Filter to these statuses (repeatable). Default: all."
    ),
    full: bool = typer.Option(
        False, "--full", help="Include the (large) job_description_text field."
    ),
) -> None:
    """Emit postings as a JSON array.

    A typed, JSON-safe dump so agents read posting rows through one loader rather
    than capturing raw SQL tool output and re-parsing it with ast.literal_eval.
    """
    engine = make_engine(_resolve_db(db))
    rows = get_postings(engine)
    if status:
        wanted = set(status)
        rows = [p for p in rows if (p.status or "new") in wanted]
    typer.echo(json.dumps([_posting_dict(p, full=full) for p in rows], indent=2))


@app.command()
def prefilter(
    db: Optional[Path] = typer.Option(None, "--db", help="Override the SQLite DB path."),
    status: str = typer.Option(
        "new", "--status", help="Status of postings to run the prefilter over."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Mark disqualified postings 'skipped' in the DB."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit the disqualified postings as JSON instead of text."
    ),
) -> None:
    """Apply the disqualifiers prefilter to DB postings — the one source of truth.

    Runs ``harness_db.disqualifiers.prefilter_disqualifies`` (the same word-bounded
    matcher every source uses) over postings of the given status so nothing
    re-implements the keyword lists in an ad-hoc script. Without ``--apply`` it
    only reports what would be dropped; with ``--apply`` it marks them 'skipped'.
    """
    engine = make_engine(_resolve_db(db))
    pf = load_prefilter()
    candidates = [p for p in get_postings(engine) if (p.status or "new") == status]
    disqualified = [
        p
        for p in candidates
        if prefilter_disqualifies(
            p.title or "", p.job_description_text or p.description_summary or "", pf
        )
    ]
    if apply:
        for p in disqualified:
            update_status(engine, p.url, "skipped")

    if json_output:
        typer.echo(json.dumps([{"url": p.url, "title": p.title} for p in disqualified], indent=2))
    else:
        verb = "Marked 'skipped'" if apply else "Would disqualify"
        typer.echo(f"{verb}: {len(disqualified)}/{len(candidates)} '{status}' postings")
        for p in disqualified:
            typer.echo(f"  - {p.title}  [{p.url}]")


if __name__ == "__main__":
    app()
