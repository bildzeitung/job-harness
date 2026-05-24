# Database Schema

The harness uses a single SQLite database at `$JOB_DATA_ROOT/jobs/postings.db`.

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
