from __future__ import annotations

from pathlib import Path
from typing import List

import typer

app = typer.Typer(help="Score job postings against the candidate profile.")


@app.command()
def main(
    batch_files: List[Path] = typer.Argument(..., help="Batch JSON files to score."),
) -> None:
    from scoring_module.scorer import score_batch

    total = 0
    for batch_file in batch_files:
        total += score_batch(str(batch_file))
    raise typer.Exit(0 if total > 0 else 1)


if __name__ == "__main__":
    app()
