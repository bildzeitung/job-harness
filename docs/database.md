# Database Schema

The harness uses a single SQLite database at `$JOB_DATA_ROOT/jobs/postings.db`.

Three tables:
- **`postings`** — one row per job posting URL; tracks the full scoring/selection/application lifecycle.
- **`companies`** — one row per hiring company; persists research findings and remote/Canada confirmation across pipeline runs.
- **`company_postings`** — links each posting to its hiring company (1 company : N postings).

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
| `platform` | TEXT | Source platform: `linkedin`, `indeed`, `adzuna`, `ziprecruiter`, `greenhouse`, `email`, `research`. |

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

The `modifier` field is the sum of three independent adjustments:

**Disqualifier modifier** (applied before full scoring; may result in `status = 'skipped'`):

| Condition | Modifier |
|-----------|----------|
| Requires specific named certification | −40 |
| Relocation required | −30 |
| US-only / geography excludes Canada | −25 |
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

---

## Table: `companies`

One row per hiring company name. Written by `job-seeker-research` (with full notes) and updated by `job-scorer` (flags + last-seen date) on every pipeline run. Read by `job-preparer` when assembling task context for workers.

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

Links each posting to its hiring company. One row per posting URL (`url` is the primary key), so the relationship is **1 company : N postings**. Written by `job-seeker` immediately after inserting a posting; the matching `companies` row is always inserted first.

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

| Agent | What it writes | Conflict rule |
|-------|---------------|---------------|
| `job-seeker-research` | All fields; `remote_confirmed = 1`, `canada_confirmed = 1`, `notes` | Overwrites flags to 1; preserves existing notes if new notes are empty |
| `job-scorer` | `remote_confirmed`, `canada_confirmed`, `last_seen_date` | Uses `MAX()` — flags can only increase (0→1), never decrease (1→0) |

### How `remote_confirmed` / `canada_confirmed` are set by the scorer

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
