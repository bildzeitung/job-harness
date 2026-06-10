"""Job posting scorer — calls Claude API with a cached system prompt."""

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

import anthropic
import httpx
from harness_db.config import get_db_path
from harness_db.disqualifiers import load_disqualifiers
from harness_db.models import Company, Posting, make_engine
from harness_db.profile import load_candidate_summary
from harness_db.vectors import find_duplicate, upsert_vector
from sqlalchemy import func
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

TODAY = date.today().isoformat()

# Optional override; when unset we fall back to the canonical
# JOB_DATA_ROOT/jobs/postings.db resolved by harness_db.config.get_db_path().
DB_PATH = os.environ.get("SQLITE_DB_PATH")
JOB_DATA_ROOT = os.environ.get("JOB_DATA_ROOT", "")
MAX_BATCH_WORKERS = 5
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2
_DB_WRITE_LOCK = threading.Lock()
JD_FETCH_MIN_LENGTH = 500
JD_TRUNCATE_LENGTH = 8000
JD_TRUNCATE_WARN_THRESHOLD = 7900
# Minimum characters of posting text before a semantic-similarity comparison is
# trustworthy (mirrors the consolidator). Below this we score normally.
_MIN_DEDUP_CHARS = 200

# Per-dimension weights (must match the rubric table in system_prompt.txt).
# base_score is computed here from these weights rather than trusting the model
# to do the `round(weighted_average * 10)` arithmetic — it intermittently emits
# the raw 1–10 average instead, collapsing ~40% of scores by 10x. See
# _compute_base_score.
_DIMENSION_WEIGHTS = {
    "technical_fit": 0.35,
    "seniority_match": 0.25,
    "domain_fit": 0.20,
    "remote_canada_confirmed": 0.10,
    "role_clarity": 0.10,
}


_DIMENSION_KEYS = tuple(_DIMENSION_WEIGHTS)


def _modifier_floor() -> int:
    """Lowest legitimate ``disqualifier_modifier`` = sum of enabled negative modifiers.

    A model can only legitimately stack the enabled negative scoring modifiers, so
    their sum is the floor; anything below it (or above 0) is a hallucination and
    is clamped. Computed once at import — the scorer process is short-lived.
    """
    try:
        mods = load_disqualifiers().get("scoring_modifiers", []) or []
    except Exception:
        return 0
    return sum(
        m["modifier"]
        for m in mods
        if isinstance(m.get("modifier"), int)
        and not isinstance(m.get("modifier"), bool)
        and m["modifier"] < 0
    )


def _render_disqualifiers(config: dict[str, Any]) -> str:
    lines = []
    for d in config.get("scoring_modifiers", []):
        examples = ", ".join(d.get("examples", []))
        suffix = f" ({examples})" if examples else ""
        lines.append(f"- {d['name']}{suffix}: {d['modifier']}")
    lines.append("- No disqualifiers: 0")
    return "\n".join(lines)


def _format_candidate_profile(profile: dict[str, Any]) -> str:
    """Build the profile text block from the structured candidate-summary.json fields."""
    req = profile.get("requirements", {})
    requirements = (
        f"Requirements: work_type={req.get('work_type', '')}; "
        f"eligibility={req.get('eligibility', '')}; "
        f"employment={', '.join(req.get('employment', []))}"
    )
    if comp_floor := req.get("comp_floor_cad"):
        requirements += (
            f"; minimum compensation=CAD {comp_floor:,} (compare listed pay in CAD-equivalent)"
        )
    lines = [
        f"Name: {profile.get('name', '')}",
        f"Headline: {profile.get('headline', '')}",
        f"Location: {profile.get('location', '')}",
        f"Experience: {profile.get('years_experience', '?')} years",
        f"Notable: {profile.get('notable', '')}",
        f"Stack: {', '.join(profile.get('stack', []))}",
        f"Domains: {', '.join(profile.get('domains', []))}",
        f"Target titles: {', '.join(profile.get('target_titles', []))}",
        requirements,
    ]
    return "\n".join(lines)


def _load_system_prompt() -> str:
    profile = load_candidate_summary()
    template = (Path(__file__).parent / "system_prompt.txt").read_text()
    template = template.replace("{{CANDIDATE_PROFILE}}", _format_candidate_profile(profile))
    return template.replace("{{DISQUALIFIERS}}", _render_disqualifiers(load_disqualifiers()))


_SYSTEM_PROMPT = _load_system_prompt()
_MODIFIER_FLOOR = _modifier_floor()


def _retry(fn, *args, **kwargs):
    """Call fn(*args, **kwargs) up to MAX_RETRIES times with exponential backoff.

    Re-raises immediately on authentication/permission errors; retries everything else.
    """
    for attempt in range(MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise
        except Exception as exc:
            if attempt == MAX_RETRIES:
                raise
            wait = RETRY_BACKOFF_BASE ** (attempt + 1)
            print(
                f"[WARN] Transient failure (attempt {attempt + 1}/{MAX_RETRIES}), "
                f"retrying in {wait}s: {exc}",
                file=sys.stderr,
            )
            time.sleep(wait)


def _make_client() -> anthropic.Anthropic:
    if api_key := os.environ.get("ANTHROPIC_API_KEY"):
        return anthropic.Anthropic(api_key=api_key)
    creds_path = Path.home() / ".claude" / ".credentials.json"
    if creds_path.exists():
        try:
            with open(creds_path) as f:
                creds = json.load(f)
            token = creds.get("claudeAiOauth", {}).get("accessToken")
            if token:
                return anthropic.Anthropic(auth_token=token)
        except Exception as e:
            print(f"[WARN] Could not load credentials from {creds_path}: {e}", file=sys.stderr)
    raise RuntimeError(
        "No Anthropic credentials found. Set ANTHROPIC_API_KEY in "
        ".claude/settings.local.json, or log in with `claude login`."
    )


def _age_modifier(post_date_str: str | None) -> int:
    if not post_date_str:
        return 0
    try:
        post_date = datetime.fromisoformat(post_date_str).date()
        days_old = (date.today() - post_date).days
        if days_old <= 3:
            return 8
        if days_old <= 7:
            return 4
        if days_old <= 14:
            return 0
        if days_old <= 30:
            return -5
        return -12
    except (ValueError, TypeError):
        return 0


def _competition_modifier(applicant_count: int | None) -> int:
    if applicant_count is None:
        return 0
    if applicant_count < 25:
        return 5
    if applicant_count <= 100:
        return 0
    if applicant_count <= 200:
        return -5
    return -10


def _fetch_jd(url: str) -> str | None:
    try:
        resp = httpx.get(
            url,
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; job-scorer/1.0)"},
        )
        if resp.status_code == 200:
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:JD_TRUNCATE_LENGTH]
        print(f"[WARN] HTTP {resp.status_code} fetching JD from {url}", file=sys.stderr)
    except Exception:
        pass
    return None


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from model response, stripping markdown code fences if present."""
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped.strip())
    return json.loads(stripped.strip())


def _posting_text(posting: dict[str, Any]) -> str:
    return (posting.get("job_description_text") or posting.get("description_summary") or "").strip()


def _reused_disqualifier(dup: Posting) -> int:
    """Recover the disqualifier component of a scored posting's stored modifier.

    The DB stores only the combined modifier (disqualifier + age + competition,
    minus a fetch-failure penalty). Strip the age/competition terms — and add back
    the fetch penalty if it was applied — to isolate the LLM's disqualifier
    judgement, which is the only modifier component that transfers to a duplicate.
    """
    mod = (
        (dup.modifier or 0)
        - _age_modifier(dup.post_date)
        - _competition_modifier(dup.applicant_count)
    )
    if (dup.scoring_notes or "").startswith("[WebFetch failed"):
        mod += 5
    return mod


def _find_scored_duplicate(engine, posting: dict[str, Any]) -> tuple[Posting, float] | None:
    """Return a (scored Posting, cosine distance) near-duplicate of `posting`, or None.

    Best-effort: a lookup failure (e.g. embedding backend down) falls back to
    normal scoring. Matches against unscored postings are ignored — there is
    nothing to reuse.
    """
    text = _posting_text(posting)
    if len(text) < _MIN_DEDUP_CHARS:
        return None
    try:
        hit = find_duplicate(engine, text, exclude_url=posting.get("url"))
    except Exception as exc:
        print(
            f"[WARN] duplicate lookup unavailable for {posting.get('url')}: {exc}", file=sys.stderr
        )
        return None
    if hit is None:
        return None
    dup_url, dist = hit
    with Session(engine) as session:
        dup = session.get(Posting, dup_url)
    if dup is None or dup.base_score is None or dup.final_score is None:
        return None
    return dup, dist


def _reuse_result(posting: dict[str, Any], dup: Posting, dist: float) -> dict[str, Any]:
    """Build a score result for `posting` by reusing a near-duplicate's verdict.

    The LLM judgement (base score, dimension scores, notes) is copied; the
    age/competition modifiers are recomputed from THIS posting so a fresher repost
    isn't penalised for the original's age.
    """
    base_score = dup.base_score or 0
    modifier = (
        _reused_disqualifier(dup)
        + _age_modifier(posting.get("post_date"))
        + _competition_modifier(posting.get("applicant_count"))
    )
    final_score = max(1, min(100, base_score + modifier))
    try:
        dimension_scores = json.loads(dup.dimension_scores) if dup.dimension_scores else {}
    except (json.JSONDecodeError, TypeError):
        dimension_scores = {}
    notes = f"[reused from near-duplicate {dup.url} · cosine {dist:.3f}] {dup.scoring_notes or ''}".strip()
    return {
        "title": posting.get("title", ""),
        "company": posting.get("company", ""),
        "url": posting.get("url", ""),
        "platform": posting.get("platform", ""),
        "post_date": posting.get("post_date"),
        "applicant_count": posting.get("applicant_count"),
        "base_score": base_score,
        "modifier": modifier,
        "final_score": final_score,
        "scoring_notes": notes,
        "dimension_scores": dimension_scores,
        "job_description_text": _posting_text(posting),
    }


def _index_vector(engine, result: dict[str, Any]) -> None:
    """Best-effort: add a freshly-scored posting's vector to `postings_vec`."""
    text = (result.get("job_description_text") or "").strip()
    if len(text) < _MIN_DEDUP_CHARS:
        return
    try:
        upsert_vector(engine, result["url"], text)
    except Exception as exc:
        print(f"[WARN] could not index {result.get('url')}: {exc}", file=sys.stderr)


def _compute_base_score(dimension_scores: dict[str, Any], fallback: Any) -> int:
    """Derive base_score (10–100) from the 1–10 dimension scores.

    The model is asked to compute `round(weighted_average * 10)` itself but does
    so unreliably — it intermittently returns the un-multiplied 1–10 average,
    which clamps the final score to ~1 (a 10x error on ~40% of postings). We own
    the arithmetic here instead. The model's own `base_score` is used only as a
    fallback when the dimension scores are missing or malformed.
    """
    try:
        weighted = sum(
            _DIMENSION_WEIGHTS[dim] * float(dimension_scores[dim]) for dim in _DIMENSION_WEIGHTS
        )
    except (KeyError, TypeError, ValueError):
        try:
            return max(1, min(100, int(fallback)))
        except (TypeError, ValueError):
            return 50
    return max(1, min(100, round(weighted * 10)))


def _default_scored() -> dict[str, Any]:
    """Neutral fallback when the model output can't be parsed after a retry."""
    return {
        "dimension_scores": dict.fromkeys(_DIMENSION_KEYS, 5),
        "base_score": 50,
        "disqualifier_modifier": 0,
        "scoring_notes": "JSON parse failed; default score applied",
    }


def _request_scores(client: anthropic.Anthropic, user_msg: str):
    return _retry(
        client.messages.create,
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )


def _call_and_parse(client: anthropic.Anthropic, user_msg: str) -> dict[str, Any] | None:
    """One API call + parse; returns the parsed dict, or None on a parse failure."""
    resp = _request_scores(client, user_msg)
    try:
        return _parse_json_response(resp.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        return None


def _clamp_disqualifier(value: Any, label: str) -> int:
    """Clamp the model's ``disqualifier_modifier`` to ``[_MODIFIER_FLOOR, 0]``.

    A non-int (or bool) becomes 0; a positive value (the model can't *add* points
    via a disqualifier) clamps to 0; a value below the enabled-modifier floor
    clamps up. Every clamp prints a ``[WARN]`` so hallucinated modifiers are
    visible without corrupting ``final_score``.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        print(
            f"[WARN] non-int disqualifier_modifier {value!r} for {label}; using 0",
            file=sys.stderr,
        )
        return 0
    if value > 0:
        print(
            f"[WARN] positive disqualifier_modifier {value} for {label}; clamping to 0",
            file=sys.stderr,
        )
        return 0
    if value < _MODIFIER_FLOOR:
        print(
            f"[WARN] disqualifier_modifier {value} below floor {_MODIFIER_FLOOR} "
            f"for {label}; clamping",
            file=sys.stderr,
        )
        return _MODIFIER_FLOOR
    return value


def _sanitize_dimension_scores(dims: Any) -> dict[str, Any]:
    """Drop dimension values outside the 1–10 range (out-of-range → treated as
    missing, so ``_compute_base_score`` takes its fallback path instead of
    weight-averaging a hallucinated value)."""
    clean: dict[str, Any] = {}
    for key, value in (dims or {}).items():
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if 1 <= numeric <= 10:
            clean[key] = value
    return clean


def _score_one(client: anthropic.Anthropic, posting: dict[str, Any]) -> dict[str, Any]:
    url = posting.get("url", "")
    title = posting.get("title", "")
    company = posting.get("company", "")
    post_date = posting.get("post_date")
    applicant_count = posting.get("applicant_count")

    jd_text = posting.get("job_description_text") or ""
    fetch_failed = False
    if len(jd_text) < JD_FETCH_MIN_LENGTH:
        fetched = _fetch_jd(url)
        if fetched:
            jd_text = fetched
            if len(jd_text) >= JD_TRUNCATE_WARN_THRESHOLD:
                print(
                    f"[WARN] JD for {company} — {title} may be truncated "
                    f"({len(jd_text)} chars fetched from URL)",
                    file=sys.stderr,
                )
        else:
            jd_text = posting.get("description_summary") or ""
            fetch_failed = True

    user_msg = f"Title: {title}\nCompany: {company}\nURL: {url}\n\nJob Description:\n{jd_text}"
    label = f"{company} — {title}"

    # Parse the model's JSON; on failure retry once with a fresh sample before
    # falling back to a neutral score, so a single bad sample doesn't strand a
    # posting at the default 50 (spec 14 A3).
    parse_failed = False
    scored = _call_and_parse(client, user_msg)
    if scored is None:
        print(f"[WARN] JSON parse failed for {label}; retrying once", file=sys.stderr)
        scored = _call_and_parse(client, user_msg)
    if scored is None:
        parse_failed = True
        scored = _default_scored()

    dimension_scores = _sanitize_dimension_scores(scored.get("dimension_scores", {}))
    base_score = _compute_base_score(dimension_scores, scored.get("base_score", 50))
    disqualifier_mod = _clamp_disqualifier(scored.get("disqualifier_modifier", 0), label)
    time_mod = _age_modifier(post_date)
    comp_mod = _competition_modifier(applicant_count)
    modifier = disqualifier_mod + time_mod + comp_mod

    notes: str = scored.get("scoring_notes", "")
    if parse_failed:
        # Tag the row so it's findable/regradable via `harness-db postings` filters.
        notes = f"[PARSE-FAILED] {notes}".strip()
    if fetch_failed:
        notes = f"[WebFetch failed; scored from summary] {notes}"
        modifier -= 5

    final_score = max(1, min(100, base_score + modifier))

    return {
        "title": title,
        "company": company,
        "url": url,
        "platform": posting.get("platform", ""),
        "post_date": post_date,
        "applicant_count": applicant_count,
        "base_score": base_score,
        "modifier": modifier,
        "final_score": final_score,
        "scoring_notes": notes,
        "dimension_scores": dimension_scores,
        "job_description_text": jd_text,
    }


def _sanitize(name: str) -> str:
    name = name.lower()
    name = re.sub(r"[^a-z0-9\s-]", "", name)
    return re.sub(r"\s+", "-", name).strip("-")


def _save_report(result: dict[str, Any], reports_dir: Path) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    fname = reports_dir / f"{_sanitize(result['company'])}-{TODAY}.json"
    with open(fname, "w") as f:
        json.dump(result, f, indent=2)


def _update_db(engine, result: dict[str, Any]) -> None:
    with _DB_WRITE_LOCK:
        with Session(engine) as session:
            r = session.execute(
                sa_update(Posting)
                .where(Posting.url == result["url"])
                .values(
                    base_score=result["base_score"],
                    modifier=result["modifier"],
                    final_score=result["final_score"],
                    scored_date=TODAY,
                    scoring_notes=result["scoring_notes"],
                    dimension_scores=json.dumps(result["dimension_scores"]),
                    job_description_text=result["job_description_text"],
                    status="scored",
                )
            )
            if r.rowcount == 0:
                raise ValueError(f"No DB row found for URL {result['url']!r}; score not persisted")
            session.commit()


def _upsert_company(engine, result: dict[str, Any]) -> None:
    """Ratchet the hiring company's remote/Canada confirmation flags.

    A posting whose `remote_canada_confirmed` dimension scores ≥ 8 explicitly
    confirms remote + Canada eligibility, so we set both flags. `MAX()` makes the
    flags monotonic (0→1, never 1→0) so a later vaguer posting cannot downgrade a
    company another posting already confirmed. `last_seen_date` always advances.
    """
    company = (result.get("company") or "").strip()
    if not company:
        return
    dims = result.get("dimension_scores") or {}
    confirmed = 1 if (dims.get("remote_canada_confirmed") or 0) >= 8 else 0
    stmt = sqlite_insert(Company).values(
        name=company,
        remote_confirmed=confirmed,
        canada_confirmed=confirmed,
        last_seen_date=TODAY,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["name"],
        set_={
            "remote_confirmed": func.max(
                func.coalesce(Company.remote_confirmed, 0), stmt.excluded.remote_confirmed
            ),
            "canada_confirmed": func.max(
                func.coalesce(Company.canada_confirmed, 0), stmt.excluded.canada_confirmed
            ),
            "last_seen_date": stmt.excluded.last_seen_date,
        },
    )
    # Best-effort, like vector indexing: the company flags are enrichment, so a
    # failure here (e.g. a legacy DB without the companies table) must not fail
    # the posting's score, which is already committed by _update_db.
    try:
        with _DB_WRITE_LOCK:
            with Session(engine) as session:
                session.execute(stmt)
                session.commit()
    except Exception as exc:
        print(f"[WARN] could not ratchet company {company!r}: {exc}", file=sys.stderr)


def _process(engine, client, reports_dir: Path, posting: dict[str, Any]) -> dict[str, Any]:
    """Score one posting, persist it, ratchet its company, and index its vector."""
    dup = _find_scored_duplicate(engine, posting)
    if dup is not None:
        dup_posting, dist = dup
        result = _reuse_result(posting, dup_posting, dist)
        reused = True
    else:
        result = _score_one(client, posting)
        reused = False
    _save_report(result, reports_dir)
    _update_db(engine, result)
    _upsert_company(engine, result)
    if not reused:
        # Reposts collapse onto the canonical posting, so only index fresh scores.
        _index_vector(engine, result)
    print(
        f"[{'REUSED' if reused else 'SCORED'}] {result['company']} — "
        f"{result['title']}: {result['final_score']}/100",
        flush=True,
    )
    return result


def _resolve_db_path() -> Path:
    if not JOB_DATA_ROOT:
        raise RuntimeError(
            "JOB_DATA_ROOT not set — cannot save reports; aborting. "
            "Add it to .claude/settings.local.json under env.JOB_DATA_ROOT."
        )
    # SQLITE_DB_PATH is an optional override; otherwise resolve the canonical
    # JOB_DATA_ROOT/jobs/postings.db the same way every other front-end does.
    return Path(DB_PATH) if DB_PATH else get_db_path()


def _reports_dir() -> Path:
    return Path(JOB_DATA_ROOT) / "jobs" / "reports"


def _posting_from_row(row: Posting) -> dict[str, Any]:
    """Project a DB Posting row into the dict shape the scorer consumes."""
    return {
        "url": row.url,
        "title": row.title or "",
        "company": row.company or "",
        "platform": row.platform or "",
        "post_date": row.post_date,
        "applicant_count": row.applicant_count,
        "description_summary": row.description_summary or "",
        "job_description_text": row.job_description_text or "",
    }


def _score_postings(engine, postings: list[dict[str, Any]]) -> int:
    """Score `postings` concurrently, persisting each. Returns the success count.

    The shared core of every entry point: `MAX_BATCH_WORKERS` already bounds
    concurrency, so callers pass the full set and let this self-batch — there is
    no need to pre-chunk the list externally.
    """
    reports_dir = _reports_dir()
    client = _make_client()

    def process(posting: dict[str, Any]) -> dict[str, Any]:
        return _process(engine, client, reports_dir, posting)

    scored_count = 0
    with ThreadPoolExecutor(max_workers=MAX_BATCH_WORKERS) as pool:
        futures = {pool.submit(process, p): p for p in postings}
        for fut in as_completed(futures):
            try:
                fut.result()
                scored_count += 1
            except Exception as exc:
                p = futures[fut]
                print(
                    f"[ERROR] {p.get('company', '?')} — {p.get('title', '?')}: {exc}",
                    file=sys.stderr,
                    flush=True,
                )
    return scored_count


def score_url(url: str) -> int:
    """Score a single posting already in the DB, by URL. Returns 1 on success, else 0.

    Powers the interactive single-posting "Score" action in the TUI and web UI,
    replacing the former job-scorer agent. Shares the batch scoring path, so it
    also reuses near-duplicate verdicts and ratchets the company flags.
    """
    engine = make_engine(_resolve_db_path())
    with Session(engine) as session:
        row = session.get(Posting, url)
        if row is None:
            print(f"[ERROR] no posting in DB for URL {url!r}", file=sys.stderr, flush=True)
            return 0
        posting = _posting_from_row(row)
    client = _make_client()
    try:
        _process(engine, client, _reports_dir(), posting)
    except Exception as exc:
        print(
            f"[ERROR] {posting['company'] or '?'} — {posting['title'] or '?'}: {exc}",
            file=sys.stderr,
            flush=True,
        )
        return 0
    print(f"[BATCH DONE] Scored 1/1 postings from {url}", flush=True)
    return 1


def score_urls(urls: list[str]) -> int:
    """Score postings already in the DB, given their URLs. Returns the success count.

    Reads each posting's stored fields (including `job_description_text`) straight
    from the DB and self-batches, so the caller — e.g. job-preparer after the
    prefilter pass — hands over a flat URL list instead of querying the DB,
    re-fetching descriptions, and writing chunked batch files by hand.
    """
    engine = make_engine(_resolve_db_path())
    postings: list[dict[str, Any]] = []
    with Session(engine) as session:
        for url in urls:
            row = session.get(Posting, url)
            if row is None:
                print(f"[ERROR] no posting in DB for URL {url!r}", file=sys.stderr, flush=True)
                continue
            postings.append(_posting_from_row(row))

    scored_count = _score_postings(engine, postings)
    print(f"[BATCH DONE] Scored {scored_count}/{len(urls)} postings from URL list", flush=True)
    return scored_count


def score_batch(batch_file: str) -> int:
    """Score all postings in a batch file. Returns count of successfully scored postings."""
    with open(batch_file) as f:
        postings = json.load(f)

    engine = make_engine(_resolve_db_path())
    scored_count = _score_postings(engine, postings)
    print(
        f"[BATCH DONE] Scored {scored_count}/{len(postings)} postings from {batch_file}", flush=True
    )
    return scored_count
