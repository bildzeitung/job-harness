from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer

app = typer.Typer(help="Score job postings against the candidate profile.")


@app.command()
def main(
    batch_files: Optional[List[Path]] = typer.Argument(None, help="Batch JSON files to score."),
    url: Optional[str] = typer.Option(
        None, "--url", help="Score a single posting by URL, read from the DB."
    ),
) -> None:
    from scoring_module.scorer import score_batch, score_url

    if url:
        if batch_files:
            typer.echo("Pass either batch files or --url, not both.", err=True)
            raise typer.Exit(2)
        total = score_url(url)
    else:
        if not batch_files:
            typer.echo("Provide batch files to score, or --url for a single posting.", err=True)
            raise typer.Exit(2)
        total = sum(score_batch(str(batch_file)) for batch_file in batch_files)

    raise typer.Exit(0 if total > 0 else 1)


if __name__ == "__main__":
    app()
