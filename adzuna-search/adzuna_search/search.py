"""Adzuna Canada job search."""

import json
import os
from pathlib import Path

import httpx

BASE_URL = "https://api.adzuna.com/v1/api/jobs/ca/search/1"

JUNIOR_KEYWORDS = ["junior", "intern", "entry level", "entry-level"]

EXCLUDE_PHRASES = ["us only", "us citizens only", "must be located in us"]


def load_candidate_summary() -> dict:
    job_data_root = os.environ.get("JOB_DATA_ROOT")
    if not job_data_root:
        raise RuntimeError("JOB_DATA_ROOT is not set")
    path = Path(job_data_root) / "candidate-summary.json"
    if not path.exists():
        raise FileNotFoundError(f"candidate-summary.json not found at {path}")
    with open(path) as f:
        return json.load(f)


def queries_from_summary(summary: dict) -> list[str]:
    return [f"{title} remote" for title in summary["target_titles"]]


def seniority_keywords_from_summary(summary: dict) -> list[str]:
    return [kw.lower() for kw in summary["seniority_keywords"]]


def _is_remote(text: str) -> bool:
    return "remote" in text.lower()


def _is_senior(title: str, seniority_keywords: list[str]) -> bool:
    t = title.lower()
    return any(kw in t for kw in seniority_keywords)


def _is_junior(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in JUNIOR_KEYWORDS)


def _is_canada_eligible(text: str) -> bool:
    t = text.lower()
    return not any(phrase in t for phrase in EXCLUDE_PHRASES)


def search(
    queries: list[str] | None = None,
    results_per_page: int = 50,
    timeout: int = 15,
) -> list[dict]:
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_API_KEY"]

    summary = load_candidate_summary()
    effective_queries = queries or queries_from_summary(summary)
    seniority_keywords = seniority_keywords_from_summary(summary)

    seen: set[str] = set()
    results: list[dict] = []

    with httpx.Client(timeout=timeout) as client:
        for q in effective_queries:
            try:
                resp = client.get(
                    BASE_URL,
                    params={
                        "app_id": app_id,
                        "app_key": app_key,
                        "results_per_page": results_per_page,
                        "what": q,
                        "full_time": 1,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print(f'[ADZUNA] Query "{q}" failed: {e}', flush=True)
                continue

            for job in data.get("results", []):
                url = job.get("redirect_url", "")
                if not url or url in seen:
                    continue

                title = job.get("title", "")
                description = job.get("description", "")
                combined = f"{title} {description}"

                if not _is_remote(combined):
                    continue
                if not _is_senior(title, seniority_keywords):
                    continue
                if _is_junior(title):
                    continue
                if not _is_canada_eligible(combined):
                    continue

                seen.add(url)
                results.append(
                    {
                        "title": title,
                        "company": job.get("company", {}).get("display_name", ""),
                        "url": url,
                        "post_date": job.get("created", "")[:10],
                        "description_summary": description[:300],
                    }
                )

    return results
