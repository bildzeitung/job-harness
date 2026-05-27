from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="Browse job postings in a TUI.")


@app.command()
def main(
    db: Optional[Path] = typer.Option(None, "--db", help="Override the SQLite DB path."),
) -> None:
    from tui.app import JobViewerApp
    from tui.config import get_db_path

    try:
        db_path = db or get_db_path()
    except RuntimeError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    if not db_path.exists():
        typer.echo(f"Database not found: {db_path}", err=True)
        raise typer.Exit(1)

    result = JobViewerApp(db_path=db_path).run()
    if isinstance(result, str):
        typer.echo(result, err=True)
        raise typer.Exit(1)
