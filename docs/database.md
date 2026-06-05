# Database Schema

The harness uses a single SQLite database at `$JOB_DATA_ROOT/jobs/postings.db`.

Three tables:
- **`postings`** — one row per job posting URL; tracks the full scoring/selection/application lifecycle.
- **`companies`** — one row per hiring company; persists research findings and remote/Canada confirmation across pipeline runs.
- **`company_postings`** — links each posting to its hiring company (1 company : N postings).

Plus one vector sidecar:
- **`postings_vec`** — a [sqlite-vec](https://github.com/asg017/sqlite-vec) virtual table holding a 1024-dim embedding per posting (keyed by URL, cosine distance), created and loaded by `make_engine`. Powers semantic repost-dedup and score-reuse; see [embeddings.md](embeddings.md).

## Table: `postings`

One row per job posting URL. The URL is the natural primary key — duplicate inserts are silently ignored (`INSERT OR IGNORE`).

```sql
CREATE TABLE postings (
    url                  TEXT     PRIMARY KEY,
    title                TEXT,
    company              TEXT,
    platform             TEXT,
    post_date            TEXT,
    applicant_count      INTEGER,
    employment_type      TEXT,
    location_note        TEXT,
    description_summary  TEXT,
    first_seen           TEXT,
    scored_date          TEXT,
    base_score           INTEGER,
    modifier             INTEGER,
    final_score          INTEGER,
    scoring_notes        TEXT,
    dimension_scores     TEXT,
    job_description_text TEXT,
    selected_date        TEXT,
    status               TEXT     DEFAULT 'new'
)
```

### Columns

#### Identity

| Column | Type | Description |
|--------|------|-------------|
| `url` | TEXT PK | Canonical job posting URL. Primary key; duplicates are ignored on insert. |
| `title` | TEXT | Job title as listed on the posting. |
| `company` | TEXT | Hiring company name. |
| `platform` | TEXT | Source platform: `linkedin`, `indeed`, `adzuna`, `ziprecruiter`, `greenhouse`, `lever`, `ashby`, `remotive`, `email`, `research`. |

#### Posting metadata

| Column | Type | Description |
|--------|------|-------------|
| `post_date` | TEXT | ISO 8601 date the posting was published. Used to calculate the age modifier. NULL if not available. |
| `applicant_count` | INTEGER | Number of applicants at time of discovery. Used to calculate the competition modifier. NULL if not available. |
| `employment_type` | TEXT | e.g. `full-time`, `contract`, `freelance`. NULL if not listed. |
| `location_note` | TEXT | Free-text location eligibility note from the search result, e.g. `"Remote, Canada OK"`. |
| `description_summary` | TEXT | 2–3 sentence summary of the role written by the seeker agent at discovery time. Used for soft-skill pre-filtering. |

#### Pipeline tracking

| Column | Type | Description |
|--------|------|-------------|
| `first_seen` | TEXT | ISO 8601 date the row was first inserted. |
| `status` | TEXT | Lifecycle status. Default `new`. See [job-states.md](job-states.md). |
| `selected_date` | TEXT | ISO 8601 date `job-preparer` marked this posting `selected`. NULL until then. |

#### Scoring

| Column | Type | Description |
|--------|------|-------------|
| `scored_date` | TEXT | ISO 8601 date scoring last ran. A posting with `scored_date` older than 7 days is re-scored on the next run. |
| `base_score` | INTEGER | Weighted composite score (1–100) before modifiers. Calculated from 5 dimensions (see below). |
| `modifier` | INTEGER | Total modifier applied (sum of disqualifier + age + competition adjustments). May be negative. |
| `final_score` | INTEGER | `clamp(base_score + modifier, 1, 100)`. The value used for ranking and selection. |
| `scoring_notes` | TEXT | Human-readable explanation of the score: dimension breakdown, disqualifiers triggered, modifiers applied. |
| `dimension_scores` | TEXT | JSON object with per-dimension scores (each 1–10, multiplied by weight to reach `base_score`). |
| `job_description_text` | TEXT | Full JD text (first 8 000 chars, HTML stripped). Cached on first score to avoid re-fetching. |

### `dimension_scores` JSON structure

```json
{
  "technical_fit":          8,
  "seniority_match":        7,
  "domain_fit":             6,
  "remote_canada_confirmed": 10,
  "role_clarity":           8
}
```

Weights used when computing `base_score`:

| Dimension | Weight |
|-----------|--------|
| `technical_fit` | 35% |
| `seniority_match` | 25% |
| `domain_fit` | 20% |
| `remote_canada_confirmed` | 10% |
| `role_clarity` | 10% |

`base_score = (Σ dimension × weight) × 10`, resulting in a 1–100 integer.

### Scoring modifiers

The `modifier` field is the sum of independent adjustments computed during scoring by the `scoring_module` script (which runs the rubric above on `claude-haiku-4-5`).

**Disqualifier modifiers** (applied by the scorer LLM during scoring; sum if several match). These are **user-configurable** — they live in the `scoring_modifiers` section of `$JOB_DATA_ROOT/disqualifiers.yaml`, not hard-coded. They are distinct from the pre-filter (which marks postings `skipped` *before* scoring; see [job-states.md](job-states.md)). The shipped defaults are:

| Condition (default name) | Modifier |
|--------------------------|----------|
| Requires a named formal certification (AWS Certified, PMP, CISSP, CKA, …) | −40 |
| Requires on-site or relocation | −30 |
| Geography excludes Canada (US-only) | −25 |
| None | 0 |

**Age modifier** (based on `post_date`):

| Post age | Modifier |
|----------|----------|
| ≤ 3 days | +8 |
| 4–7 days | +4 |
| 8–14 days | 0 |
| 15–30 days | −5 |
| > 30 days | −12 |
| Unknown | 0 |

**Competition modifier** (based on `applicant_count`):

| Applicant count | Modifier |
|-----------------|----------|
| < 25 | +5 |
| 25–100 | 0 |
| 101–200 | −5 |
| > 200 | −10 |
| Unknown | 0 |

**Fetch-failure modifier** (applied in code when the full JD cannot be retrieved):

| Condition | Modifier |
|-----------|----------|
| Full JD could not be fetched — posting scored from its short `description_summary` instead | −5 |

---

## Table: `companies`

One row per hiring company name. Populated during the **Seek** stage: `consolidate_module` creates the row (name + `last_seen_date`) when a posting is first inserted, the platform searchers (e.g. `job-seeker-adzuna`) enrich it with `canada_confirmed` / `last_seen_date`, and `job-seeker-research` adds `notes` plus the remote/Canada flags. `job-seeker-company` later fills `careers_url` / `fetch_notes`. Read by `job-preparer` when assembling task context for workers.

> Note: the batch `scoring_module` used by the main pipeline updates **only** the `postings` row — it does not touch `companies`. The standalone `job-scorer` agent (single-posting path, not the batch scorer) is the one that upserts company flags; see below.

```sql
CREATE TABLE companies (
    name               TEXT     PRIMARY KEY,
    remote_confirmed   INTEGER  DEFAULT 0,
    canada_confirmed   INTEGER  DEFAULT 0,
    notes              TEXT,
    researched_date    TEXT,
    last_seen_date     TEXT,
    careers_url        TEXT,
    fetch_notes        TEXT
)
```

### Columns

| Column | Type | Description |
|--------|------|-------------|
| `name` | TEXT PK | Company name as it appears in job postings. Primary key. |
| `remote_confirmed` | INTEGER | `1` if any verified posting or research confirmed the company offers fully remote work; `0` otherwise. Never downgraded — once confirmed, stays confirmed. |
| `canada_confirmed` | INTEGER | `1` if any verified posting or research confirmed Canada-eligibility; `0` otherwise. Never downgraded. |
| `notes` | TEXT | 1–2 sentence research summary: funding stage, domain focus, team size, hiring signals. Written by `job-seeker-research`; preserved on subsequent upserts if non-empty. |
| `researched_date` | TEXT | ISO 8601 date `job-seeker-research` last wrote a notes entry for this company. |
| `last_seen_date` | TEXT | ISO 8601 date any pipeline agent last encountered a posting from this company. Updated by `job-scorer` on every scoring run. |
| `careers_url` | TEXT | At least one URL to where the company posts its jobs (careers page or ATS board). Written by `job-seeker-company`. NULL until researched. |
| `fetch_notes` | TEXT | Notes on how to fetch jobs and job descriptions from the company's site (ATS type, API endpoint, pagination), or the reason the careers URL could not be found. Written by `job-seeker-company`. |

---

## Table: `company_postings`

Links each posting to its hiring company. One row per posting URL (`url` is the primary key), so the relationship is **1 company : N postings**. Written by `consolidate_module` in the same transaction that inserts the posting; the matching `companies` row is always inserted first (`INSERT … ON CONFLICT DO NOTHING`).

```sql
CREATE TABLE company_postings (
    url           TEXT     PRIMARY KEY REFERENCES postings(url),
    company_name  TEXT     REFERENCES companies(name)
)
```

| Column | Type | Description |
|--------|------|-------------|
| `url` | TEXT PK | Posting URL. Foreign key to `postings.url`. Primary key — each posting links to exactly one company. |
| `company_name` | TEXT | Hiring company name. Foreign key to `companies.name`. Indexed for company → postings lookups. |

### Writers and flag promotion rules

| Writer | What it writes | Conflict rule |
|--------|---------------|---------------|
| `consolidate_module` (Seek) | `name`, `last_seen_date` on first insert | `INSERT … ON CONFLICT DO NOTHING` — never overwrites an existing row |
| platform searchers (e.g. `job-seeker-adzuna`) | `canada_confirmed`, `last_seen_date` | Uses `MAX()` — flags only increase (0→1); `last_seen_date` advances to the newer date |
| `job-seeker-research` | `notes`, `remote_confirmed = 1`, `canada_confirmed = 1`, `researched_date` | Overwrites flags to 1; preserves existing notes if new notes are empty |
| `job-seeker-company` | `careers_url`, `fetch_notes` | Fills in research findings |
| `job-scorer` agent (standalone single-posting path only) | `remote_confirmed`, `canada_confirmed`, `last_seen_date` | Uses `MAX()` — flags can only increase (0→1), never decrease (1→0) |

### How `remote_confirmed` / `canada_confirmed` are set by the standalone `job-scorer` agent

> This applies to the standalone `job-scorer` agent only. The batch `scoring_module` used by the main `job-preparer` pipeline does **not** write to `companies`.

The scorer's `remote_canada_confirmed` dimension is scored 1–10. If that dimension score is **≥ 8**, the posting explicitly states remote + Canada eligibility and both flags are set to `1` on upsert. Below 8, both are set to `0` in the upsert, but `MAX()` ensures an existing `1` is never overwritten.

### How `company_notes` flows to cover letters

```
job-seeker-research  →  companies.notes
                               ↓
job-preparer  (SELECT notes FROM companies WHERE name IN (...))
                               ↓
TaskCreate.description  (company_notes field)
                               ↓
job-pipeline-worker  →  resume-tailor prompt + cover-letter-creator prompt
```
