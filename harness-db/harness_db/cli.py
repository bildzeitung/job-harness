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
from typing import Optional

import typer

from harness_db.config import get_db_path
from harness_db.models import make_engine
from harness_db.profile import load_candidate_summary
from harness_db.queries import get_postings
from harness_db.report import render_report, report_data

app = typer.Typer(help="Job-harness DB tools.", no_args_is_help=True)

sources_app = typer.Typer(help="Manage job-search source selection.", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

disq_app = typer.Typer(
    help="Manage hard disqualifiers (prefilter + scoring).", no_args_is_help=True
)
app.add_typer(disq_app, name="disqualifiers")


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


@sources_app.command("list")
def sources_list(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """List sources with the user's enabled flag."""
    from harness_db.sources_store import list_sources

    for s in list_sources(uid):
        mark = "x" if s.enabled else " "
        typer.echo(f"[{mark}] {s.source_id:<13} {s.description}")


@sources_app.command("enabled")
def sources_enabled(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Print the enabled sources as JSON: ``{"enabled": [...]}``.

    This is the job-seeker's read path. It runs the full schema seed + one-time
    file import, so the first pipeline run migrates an existing install.
    """
    from harness_db.seed import ensure_schema_and_seed
    from harness_db.sources_store import enabled_source_ids

    ensure_schema_and_seed()
    typer.echo(json.dumps({"enabled": enabled_source_ids(uid)}))


@sources_app.command("enable")
def sources_enable(
    source_id: str = typer.Argument(..., help="Source id, e.g. linkedin."),
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Enable a source for the user."""
    from harness_db.sources_store import set_enabled

    set_enabled(source_id, True, uid)
    typer.echo(f"enabled {source_id}")


@sources_app.command("disable")
def sources_disable(
    source_id: str = typer.Argument(..., help="Source id, e.g. linkedin."),
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Disable a source for the user."""
    from harness_db.sources_store import set_enabled

    set_enabled(source_id, False, uid)
    typer.echo(f"disabled {source_id}")


@disq_app.command("prefilter")
def disq_prefilter(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Print the user's effective prefilter section as JSON (job-preparer's read path)."""
    from harness_db.disqualifiers import load_prefilter
    from harness_db.seed import ensure_schema_and_seed

    ensure_schema_and_seed()
    typer.echo(json.dumps(load_prefilter(uid), indent=2))


@disq_app.command("show")
def disq_show(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Print the full effective disqualifiers (prefilter + scoring_modifiers) as JSON."""
    from harness_db.disqualifiers import load_disqualifiers
    from harness_db.seed import ensure_schema_and_seed

    ensure_schema_and_seed()
    typer.echo(json.dumps(load_disqualifiers(uid), indent=2))


if __name__ == "__main__":
    app()
