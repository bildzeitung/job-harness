from __future__ import annotations

from datetime import date

import typer

app = typer.Typer(
    help="Merge per-platform job-seeker temp files, dedup against the DB, write the audit log, and insert new rows."
)


@app.command()
def main(
    batch_date: str = typer.Option(
        date.today().isoformat(),
        "--date",
        "-d",
        help="Batch date (YYYY-MM-DD). Defaults to today.",
    ),
) -> None:
    from consolidate_module.consolidator import consolidate

    inserted = consolidate(batch_date)
    raise typer.Exit(0 if inserted >= 0 else 1)


if __name__ == "__main__":
    app()
