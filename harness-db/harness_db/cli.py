"""Command-line entry point for harness DB operations.

``harness-db report`` prints (or, with ``--json``, emits) the status summary,
score distribution, and top-N fit table for the canonical DB (resolved via
:func:`harness_db.config.get_db_path`, overridable with ``--db``). ``harness-db
candidate`` prints a field from ``candidate-summary.json`` so agents read the
shared profile through one loader instead of inline JSON parsing. Subcommands are
added under one parser so future helpers share the same DB-resolution and error
handling.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness_db.config import get_db_path
from harness_db.models import make_engine
from harness_db.profile import load_candidate_summary
from harness_db.queries import get_postings
from harness_db.report import render_report, report_data


def _resolve_db(db: str | None) -> Path:
    db_path = Path(db) if db else get_db_path()
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")
    return db_path


def _cmd_report(args: argparse.Namespace) -> None:
    engine = make_engine(_resolve_db(args.db))
    postings = get_postings(engine)
    if args.json:
        print(
            json.dumps(
                report_data(
                    postings,
                    min_score=args.min_score,
                    top=args.top,
                    scored_on=args.scored_on,
                ),
                indent=2,
            )
        )
    else:
        print(
            render_report(
                postings,
                min_score=args.min_score,
                top=args.top,
                scored_on=args.scored_on,
            )
        )


def _cmd_candidate(args: argparse.Namespace) -> None:
    summary = load_candidate_summary()
    value = summary.get(args.field)
    if value is None:
        raise SystemExit(f"Field {args.field!r} not in candidate-summary.json")
    value = str(value)
    if args.filename_safe:
        value = value.replace(" ", "_")
    print(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harness-db", description="Job-harness DB tools.")
    sub = parser.add_subparsers(dest="command", required=True)

    # Options shared by every subcommand (inherited so they accept `--db` after
    # the subcommand name, e.g. `harness-db report --db ...`).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", help="Override the SQLite DB path.")

    report = sub.add_parser(
        "report",
        parents=[common],
        help="Status summary, score distribution, and top fits.",
    )
    report.add_argument("--min-score", type=int, default=75, help="Minimum score for top list.")
    report.add_argument("--top", type=int, default=15, help="How many top postings to list.")
    report.add_argument(
        "--scored-on",
        help="Limit top list to postings scored on this date prefix, e.g. 2026-05-29.",
    )
    report.add_argument(
        "--json",
        action="store_true",
        help="Emit structured JSON (ranked rows + counts) instead of the text table.",
    )
    report.set_defaults(func=_cmd_report)

    candidate = sub.add_parser(
        "candidate",
        help="Print a field from candidate-summary.json (default: name).",
    )
    candidate.add_argument(
        "--field",
        default="name",
        help="Which candidate-summary.json field to print (default: name).",
    )
    candidate.add_argument(
        "--filename-safe",
        action="store_true",
        help="Replace spaces with underscores (e.g. for resume PDF filenames).",
    )
    candidate.set_defaults(func=_cmd_candidate)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv if argv is not None else sys.argv[1:])
    try:
        args.func(args)
    except (RuntimeError, FileNotFoundError) as e:  # config / profile resolution failures
        raise SystemExit(f"Error: {e}")


if __name__ == "__main__":
    main()
