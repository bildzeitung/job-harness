"""Job posting scorer — calls Claude API with a cached system prompt."""

import json
import os
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from pathlib import Path
from typing import Any

import anthropic
import httpx

TODAY = date.today().isoformat()

DB_PATH = os.environ.get("SQLITE_DB_PATH", "/home/dmklein/mcp-sqlite/job-search.db")
JOB_DATA_ROOT = os.environ.get("JOB_DATA_ROOT", "")


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
        except Exception:
            pass
    raise RuntimeError(
        "No Anthropic credentials found. Set ANTHROPIC_API_KEY in "
        ".claude/settings.local.json, or log in with `claude login`."
    )

_SYSTEM_PROMPT = """You are a job-fit scorer. Score a job posting against this candidate profile and return JSON only.

## Candidate Profile
- Principal/Staff Engineer, 20+ years total, 13 at Oracle (OCI, Public Cloud, Health & AI)
- Stack: Python, Java, C#, OCI, Azure, AWS, Kubernetes, Terraform, Helm, FHIR, GraphQL, SQL
- Location: Thunder Bay, ON, Canada — must be fully remote
- No formal certifications (no AWS Certified, Azure Administrator, GCP Associate, PMP, CISSP, CKA)
- Domains: healthcare/FHIR, cloud infrastructure, distributed systems, AI/ML platform engineering

## Scoring Rubric (score each dimension 1–10)
| Dimension           | Weight | What to look for                            |
|---------------------|--------|---------------------------------------------|
| technical_fit       |   35%  | Stack overlap with candidate skills         |
| seniority_match     |   25%  | Principal / Staff / Architect level         |
| domain_fit          |   20%  | Cloud, healthcare, AI/ML, distributed sys   |
| remote_canada_confirmed | 10% | Explicit in posting (not assumed)          |
| role_clarity        |   10%  | Clear responsibilities, not vague           |

base_score = round(weighted_average * 10)

## Disqualifiers (apply modifier, explain in notes; sum if multiple)
- Requires a named formal certification (AWS Certified, Azure Administrator, GCP Associate, PMP, CISSP, CKA, etc.): -40
- Requires on-site or relocation: -30
- Geography excludes Canada (US-only auth language, US city/state with no remote mention, "US-based candidates only"): -25
- No disqualifiers: 0

## Output — JSON only, no markdown, no explanation
{"dimension_scores": {"technical_fit": N, "seniority_match": N, "domain_fit": N, "remote_canada_confirmed": N, "role_clarity": N}, "base_score": N, "disqualifier_modifier": N, "scoring_notes": "brief notes"}"""


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
            url, timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; job-scorer/1.0)"},
        )
        if resp.status_code == 200:
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            return text[:8000]
    except Exception:
        pass
    return None


def _score_one(client: anthropic.Anthropic, posting: dict[str, Any]) -> dict[str, Any]:
    url = posting.get("url", "")
    title = posting.get("title", "")
    company = posting.get("company", "")
    post_date = posting.get("post_date")
    applicant_count = posting.get("applicant_count")

    jd_text = posting.get("job_description_text") or ""
    fetch_failed = False
    if len(jd_text) < 500:
        fetched = _fetch_jd(url)
        if fetched:
            jd_text = fetched
        else:
            jd_text = posting.get("description_summary") or ""
            fetch_failed = True

    user_msg = f"Title: {title}\nCompany: {company}\nURL: {url}\n\nJob Description:\n{jd_text}"

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=[{"type": "text", "text": _SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_msg}],
    )

    try:
        scored = json.loads(resp.content[0].text)
    except (json.JSONDecodeError, IndexError, AttributeError):
        scored = {
            "dimension_scores": {k: 5 for k in
                                  ("technical_fit", "seniority_match", "domain_fit",
                                   "remote_canada_confirmed", "role_clarity")},
            "base_score": 50,
            "disqualifier_modifier": 0,
            "scoring_notes": "JSON parse failed; default score applied",
        }

    base_score: int = scored.get("base_score", 50)
    disqualifier_mod: int = scored.get("disqualifier_modifier", 0)
    time_mod = _age_modifier(post_date)
    comp_mod = _competition_modifier(applicant_count)
    modifier = disqualifier_mod + time_mod + comp_mod

    notes: str = scored.get("scoring_notes", "")
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
        "dimension_scores": scored.get("dimension_scores", {}),
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


def _update_db(result: dict[str, Any]) -> None:
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            """UPDATE postings
               SET base_score = ?, modifier = ?, final_score = ?,
                   scored_date = ?, scoring_notes = ?,
                   dimension_scores = ?, job_description_text = ?,
                   status = 'scored'
               WHERE url = ?""",
            (
                result["base_score"],
                result["modifier"],
                result["final_score"],
                TODAY,
                result["scoring_notes"],
                json.dumps(result["dimension_scores"]),
                result["job_description_text"],
                result["url"],
            ),
        )
        conn.commit()
    finally:
        conn.close()


def score_batch(batch_file: str, max_workers: int = 5) -> int:
    """Score all postings in a batch file. Returns count of successfully scored postings."""
    with open(batch_file) as f:
        postings = json.load(f)

    reports_dir = Path(JOB_DATA_ROOT) / "jobs" / "reports" if JOB_DATA_ROOT else None
    if not JOB_DATA_ROOT:
        print("[WARN] JOB_DATA_ROOT not set; reports will not be saved", file=sys.stderr)

    client = _make_client()

    def process(posting: dict[str, Any]) -> dict[str, Any]:
        result = _score_one(client, posting)
        if reports_dir:
            _save_report(result, reports_dir)
        _update_db(result)
        print(f"[SCORED] {result['company']} — {result['title']}: {result['final_score']}/100",
              flush=True)
        return result

    scored_count = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(process, p): p for p in postings}
        for fut in as_completed(futures):
            try:
                fut.result()
                scored_count += 1
            except Exception as exc:
                p = futures[fut]
                print(f"[ERROR] {p.get('company', '?')} — {p.get('title', '?')}: {exc}",
                      file=sys.stderr, flush=True)

    print(f"[BATCH DONE] Scored {scored_count}/{len(postings)} postings from {batch_file}",
          flush=True)
    return scored_count
