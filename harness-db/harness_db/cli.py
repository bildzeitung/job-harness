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

sources_app = typer.Typer(help="Manage job-search source selection.", no_args_is_help=True)
app.add_typer(sources_app, name="sources")

disq_app = typer.Typer(
    help="Manage hard disqualifiers (prefilter + scoring).", no_args_is_help=True
)
app.add_typer(disq_app, name="disqualifiers")

roles_app = typer.Typer(
    help="Manage target roles (the DB is the source of truth; `show` renders them).",
    no_args_is_help=True,
)
app.add_typer(roles_app, name="target-roles")

user_app = typer.Typer(help="Manage users (profiles) and the active user.", no_args_is_help=True)
app.add_typer(user_app, name="user")

config_app = typer.Typer(help="Manage per-user configuration values.", no_args_is_help=True)
app.add_typer(config_app, name="config")

companies_app = typer.Typer(
    help="Record hiring companies seen by the searchers.", no_args_is_help=True
)
app.add_typer(companies_app, name="companies")


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


@roles_app.command("list")
def roles_list(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """List target-role items grouped by kind, with the user's enabled flag."""
    from harness_db.seed import ensure_schema_and_seed
    from harness_db.target_roles import list_target_roles

    ensure_schema_and_seed()
    for item in list_target_roles(uid):
        mark = "x" if item.enabled else " "
        custom = " *" if item.custom else ""
        typer.echo(f"[{mark}] {item.id:>4} {item.kind:<8} {item.value}{custom}")


@roles_app.command("show")
def roles_show(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Render the target-roles markdown from the DB to stdout (no file written).

    This is what the pipeline reads at runtime — the DB is the source of truth,
    so consumers take it straight from here instead of a generated file.
    """
    from harness_db.seed import ensure_schema_and_seed
    from harness_db.target_roles import render_target_roles_md

    ensure_schema_and_seed()
    typer.echo(render_target_roles_md(uid))


@roles_app.command("generate")
def roles_generate(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
    path: Optional[Path] = typer.Option(
        None, "--path", help="Output path (default: $JOB_DATA_ROOT/target-roles.md)."
    ),
) -> None:
    """Write target-roles.md from the DB (optional escape hatch; the pipeline
    reads from the DB directly via `target-roles show`, not this file)."""
    from harness_db.seed import ensure_schema_and_seed
    from harness_db.target_roles import write_target_roles_md

    ensure_schema_and_seed()
    written = write_target_roles_md(uid, path)
    typer.echo(f"wrote {written}")


# ── companies ─────────────────────────────────────────────────────────────────


def _load_batch_postings(path: Path) -> list[dict]:
    """Postings list from a consolidator-schema object or a bare array file."""
    data = json.loads(path.read_text())
    if isinstance(data, dict):
        postings = data.get("postings", [])
    else:
        postings = data
    return postings if isinstance(postings, list) else []


@companies_app.command("seen")
def companies_seen(
    files: List[Path] = typer.Argument(
        ..., help="One or more jobs/{platform}-{date}.json batch files."
    ),
    platform: Optional[str] = typer.Option(
        None,
        "--platform",
        help="Fallback platform when a file/posting omits its 'platform' key.",
    ),
    date: Optional[str] = typer.Option(
        None, "--date", help="Batch date for last_seen (default: today)."
    ),
    db: Optional[Path] = typer.Option(None, "--db", help="Override the SQLite DB path."),
) -> None:
    """Upsert company records from searcher batch files (one call per agent).

    Applies the per-platform flag policy in ``harness_db.companies`` (remote /
    Canada ratchets, last_seen advance, notes fill-or-overwrite), replacing the
    per-company ``INSERT … ON CONFLICT`` SQL the searchers hand-wrote.
    """
    from datetime import date as _date

    from harness_db import companies
    from harness_db.seed import ensure_schema_and_seed

    engine = ensure_schema_and_seed(make_engine(_resolve_db(db)), import_existing=False)
    batch_date = date or _date.today().isoformat()

    postings: list[dict] = []
    for f in files:
        try:
            postings.extend(_load_batch_postings(f))
        except (OSError, json.JSONDecodeError) as e:
            typer.echo(f"Warning: skipping {f}: {e}", err=True)

    try:
        result = companies.record_seen(engine, postings, batch_date, default_platform=platform)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(
        f"[COMPANIES:SEEN] {result['companies']} companies "
        f"({result['inserted']} new) from {len(files)} file(s)"
    )


# ── user management ───────────────────────────────────────────────────────────


@user_app.command("add")
def user_add(
    uid: str = typer.Argument(..., help="New user id."),
    use: bool = typer.Option(False, "--use", help="Also make this the active user."),
) -> None:
    """Create a user (with default selections) and optionally activate it."""
    from sqlalchemy.orm import Session

    from harness_db import users
    from harness_db.config import set_active_uid
    from harness_db.seed import ensure_schema_and_seed, ensure_user_defaults

    engine = ensure_schema_and_seed()
    try:
        users.create_user(engine, uid)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    with Session(engine) as session:
        ensure_user_defaults(session, uid)
        session.commit()
    if use:
        set_active_uid(uid)
    typer.echo(f"created user {uid}" + (" (active)" if use else ""))


@user_app.command("list")
def user_list() -> None:
    """List users; the active user (dotfile) is marked with '*'."""
    from harness_db import users
    from harness_db.config import get_active_uid
    from harness_db.seed import ensure_schema_and_seed

    engine = ensure_schema_and_seed()
    active = get_active_uid()
    for u in users.list_users(engine):
        mark = "*" if u.uid == active else " "
        state = "active" if u.active else "inactive"
        typer.echo(f"{mark} {u.uid:<20} {state}")


@user_app.command("use")
def user_use(uid: str = typer.Argument(..., help="User id to make active.")) -> None:
    """Set the active user (writes the .active-user dotfile beside the DB)."""
    from harness_db import users
    from harness_db.config import set_active_uid
    from harness_db.seed import ensure_schema_and_seed

    engine = ensure_schema_and_seed()
    if not users.user_exists(engine, uid):
        typer.echo(f"Error: unknown user {uid!r} (create it with 'user add')", err=True)
        raise typer.Exit(1)
    set_active_uid(uid)
    typer.echo(f"active user is now {uid}")


@user_app.command("show")
def user_show() -> None:
    """Print the active user id."""
    from harness_db.config import get_active_uid

    typer.echo(get_active_uid())


@user_app.command("set-active")
def user_set_active(
    uid: str = typer.Argument(..., help="User id."),
    active: bool = typer.Option(True, "--active/--inactive", help="Set the active flag."),
) -> None:
    """Toggle a user's active flag."""
    from harness_db import users
    from harness_db.seed import ensure_schema_and_seed

    engine = ensure_schema_and_seed()
    try:
        users.set_active(engine, uid, active)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{uid}: {'active' if active else 'inactive'}")


# ── config values ─────────────────────────────────────────────────────────────


@config_app.command("list")
def config_list(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Show every config key and the user's resolved value (DB → env)."""
    from harness_db.config_store import list_config
    from harness_db.seed import ensure_schema_and_seed

    ensure_schema_and_seed()
    for key, value in list_config(uid).items():
        typer.echo(f"{key:<16} {value if value is not None else '(unset)'}")


@config_app.command("get")
def config_get(
    key: str = typer.Argument(..., help="Config key, e.g. RESUME_FILE."),
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Print a single resolved config value."""
    from harness_db.config_store import get_config_optional

    value = get_config_optional(key, uid)
    if value is None:
        typer.echo(f"Error: {key} is not set", err=True)
        raise typer.Exit(1)
    typer.echo(value)


@config_app.command("set")
def config_set(
    key: str = typer.Argument(..., help="Config key, e.g. RESUME_FILE."),
    value: str = typer.Argument(..., help="Value to store."),
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """Set a config value for the user."""
    from harness_db.config_store import set_config

    set_config(key, value, uid)
    typer.echo(f"set {key}")


# ── disqualifier editing ──────────────────────────────────────────────────────


@disq_app.command("list")
def disq_list(
    uid: Optional[str] = typer.Option(None, "--uid", help="Target user (default: active user)."),
) -> None:
    """List prefilter rules and scoring blocks with enabled flags and ids."""
    from harness_db.disqualifiers import list_prefilter_rules, list_scoring_blocks
    from harness_db.seed import ensure_schema_and_seed

    ensure_schema_and_seed()
    typer.echo("# Prefilter rules")
    for r in list_prefilter_rules(uid):
        mark = "x" if r.enabled else " "
        custom = " *" if r.custom else ""
        typer.echo(f"[{mark}] {r.id:>4} {r.category:<24} {r.value}{custom}")
    typer.echo("\n# Scoring modifier blocks")
    for b in list_scoring_blocks(uid):
        mark = "x" if b.enabled else " "
        custom = " *" if b.custom else ""
        typer.echo(f"[{mark}] {b.id:>4} ({b.modifier:>4}) {b.name}{custom}")


@disq_app.command("enable")
def disq_enable(
    rule_id: int = typer.Argument(..., help="Prefilter rule id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Enable a prefilter rule for the user."""
    from harness_db.disqualifiers import set_prefilter_enabled

    set_prefilter_enabled(rule_id, True, uid)
    typer.echo(f"enabled prefilter rule {rule_id}")


@disq_app.command("disable")
def disq_disable(
    rule_id: int = typer.Argument(..., help="Prefilter rule id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Disable a prefilter rule for the user."""
    from harness_db.disqualifiers import set_prefilter_enabled

    set_prefilter_enabled(rule_id, False, uid)
    typer.echo(f"disabled prefilter rule {rule_id}")


@disq_app.command("add")
def disq_add(
    category: str = typer.Argument(
        ...,
        help="One of: description_phrases, title_terms, "
        "title_terms_unless_senior, seniority_exceptions.",
    ),
    value: str = typer.Argument(..., help="The keyword/phrase."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Add a custom prefilter rule."""
    from harness_db.disqualifiers import add_prefilter_rule

    try:
        rid = add_prefilter_rule(category, value, uid)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"added prefilter rule {rid}")


@disq_app.command("remove")
def disq_remove(
    rule_id: int = typer.Argument(..., help="Custom prefilter rule id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Delete a custom prefilter rule (built-ins can only be disabled)."""
    from harness_db.disqualifiers import delete_prefilter_rule

    try:
        delete_prefilter_rule(rule_id, uid)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"removed prefilter rule {rule_id}")


# ── target-role editing ───────────────────────────────────────────────────────


@roles_app.command("enable")
def roles_enable(
    item_id: int = typer.Argument(..., help="Target-role item id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Enable a target-role item for the user."""
    from harness_db.target_roles import set_enabled

    set_enabled(item_id, True, uid)
    typer.echo(f"enabled target role {item_id}")


@roles_app.command("disable")
def roles_disable(
    item_id: int = typer.Argument(..., help="Target-role item id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Disable a target-role item for the user."""
    from harness_db.target_roles import set_enabled

    set_enabled(item_id, False, uid)
    typer.echo(f"disabled target role {item_id}")


@roles_app.command("add")
def roles_add(
    kind: str = typer.Argument(..., help="One of: title, keyword, domain."),
    value: str = typer.Argument(..., help="The role title / keyword / domain."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Add a custom target-role item."""
    from harness_db.target_roles import add_target_role

    try:
        rid = add_target_role(kind, value, uid)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"added target role {rid}")


@roles_app.command("remove")
def roles_remove(
    item_id: int = typer.Argument(..., help="Custom target-role item id."),
    uid: Optional[str] = typer.Option(None, "--uid"),
) -> None:
    """Delete a custom target-role item (built-ins can only be disabled)."""
    from harness_db.target_roles import delete_target_role

    try:
        delete_target_role(item_id, uid)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"removed target role {item_id}")


if __name__ == "__main__":
    app()
