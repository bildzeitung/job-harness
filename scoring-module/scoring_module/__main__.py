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
    urls_file: Optional[Path] = typer.Option(
        None,
        "--urls-file",
        help=(
            "Score every posting whose URL is listed (one per line) in this file, "
            "reading each from the DB. Self-batches — no manual chunking needed."
        ),
    ),
) -> None:
    from scoring_module.scorer import score_batch, score_url, score_urls

    modes = [bool(url), bool(urls_file), bool(batch_files)]
    if sum(modes) > 1:
        typer.echo("Pass exactly one of: batch files, --url, or --urls-file.", err=True)
        raise typer.Exit(2)

    if url:
        total = score_url(url)
    elif urls_file:
        urls = [line.strip() for line in urls_file.read_text().splitlines() if line.strip()]
        if not urls:
            typer.echo(f"No URLs found in {urls_file}.", err=True)
            raise typer.Exit(2)
        total = score_urls(urls)
    elif batch_files:
        total = sum(score_batch(str(batch_file)) for batch_file in batch_files)
    else:
        typer.echo(
            "Provide batch files, --url for a single posting, or --urls-file for a URL list.",
            err=True,
        )
        raise typer.Exit(2)

    raise typer.Exit(0 if total > 0 else 1)


if __name__ == "__main__":
    app()
