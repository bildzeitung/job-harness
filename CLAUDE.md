# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A [RenderCV](https://github.com/rendercv/rendercv)-based resume project. The source of truth is the CV YAML file, validated against the RenderCV v2.8 JSON schema. All outputs (`rendercv_output/`) are generated artifacts — never edit them directly.

## Configuration

The resume file path is configured as an environment variable. Each user sets this in their local `.claude/settings.local.json` (gitignored — never committed):

```json
{
  "env": {
    "ADZUNA_APP_ID": "**REDACTED**",
    "ADZUNA_API_KEY": "**REDACTED**",
    "JOB_DATA_ROOT": "/absolute/path/to/job-data",
    "RESUME_FILE": "/absolute/path/to/Your_Name_CV.yaml"
  }
}
```

Agents read this at runtime via `bash -c 'echo $RESUME_FILE'`. This makes the harness shareable — clone the repo, set `RESUME_FILE`, and it works for any resume.

**`ANTHROPIC_API_KEY` is not required.** The `scoring_module` Python script authenticates by falling back to the OAuth token in `~/.claude/.credentials.json` (the same session Claude Code uses). If you do have an API key, setting it takes priority.

## Rendering

Editing the CV YAML automatically triggers a render via a PostToolUse hook. To render manually:

```bash
rendercv render "$RESUME_FILE"
```

Outputs land in `rendercv_output/` as PDF, HTML, Markdown, Typst, and page images.

## Agents

Twelve agents are configured in [.claude/agents/](.claude/agents/):

**CV agents:**
- **resume-evaluator** — Runs the CV through achievement reframing, 10-second scan test, and red flag detection. Use via `/resume-work` skill.
- **resume-tailor** — Tailors the CV for a specific job posting (ATS bypass, gap analysis, keyword embedding).
- **cover-letter-creator** — Writes a cover letter from the CV + a job description.

**Job search harness agents** (see `harness/` for diagram and data):
- **job-seeker** — Orchestrator: spawns six platform searchers in parallel, merges results, deduplicates against the SQLite DB, inserts new postings, saves an audit log to `job-data/jobs/search-YYYY-MM-DD.json`.
- **job-seeker-linkedin** — Searches LinkedIn via the LinkedIn MCP server (`mcp__linkedin__search_jobs`).
- **job-seeker-indeed** — Searches Indeed via the Indeed MCP server.
- **job-seeker-adzuna** — Searches Adzuna Canada via the Adzuna REST API (credentials in `$ADZUNA_APP_ID` / `$ADZUNA_API_KEY`).
- **job-seeker-email** — Reads the most recent LinkedIn job alert email from Gmail (`jobalerts-noreply@linkedin.com`), extracts postings, and labels the email with `AI`. Requires Gmail MCP OAuth. Use via `/job-search-email` skill — not part of the main pipeline.
- **job-seeker-research** — Finds companies actively hiring via non-LinkedIn/non-Indeed sources (Greenhouse, Lever, Wellfound, funded startups). Acts as a recruitment expert targeting growing and recently funded companies.
- **job-scorer** — Scores a single job posting 1–100 against the CV. Saves reports to `job-data/jobs/reports/`.
- **job-preparer** — Team lead: scores all postings, presents top 5 (min score 75) to the user for selection, creates an agent team, assigns one task per selected job, monitors workers, tears down the team when done. Writes a final report with URLs to `job-data/output/YYYY-MM-DD/final-report.md`.
- **job-pipeline-worker** — Team worker: claims a job task, runs resume-tailor → rendercv PDF → cover-letter-creator → rendercv PDF, reports results to the lead, loops until no tasks remain. Not invoked directly — spawned by job-preparer.

CV agents (`resume-evaluator`, `resume-tailor`, `cover-letter-creator`) use `model: opus`. Pipeline agents use `model: sonnet`.

## General Directives

1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.

2. Simplest solution first. Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.

3. Flag uncertainty explicitly. If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

## Workflows

**General CV cleanup:** `/resume-work` — spawns the evaluator and applies every suggested edit in one pass, no confirmation prompts.

**Job-specific customization:** Spawn the `resume-tailor` agent with the job description. It will tailor the YAML directly.

**Cover letter:** Spawn the `cover-letter-creator` agent with the job description.

**Full job search run:**
1. Spawn `job-seeker` — searches LinkedIn + Indeed + Adzuna + ZipRecruiter + Greenhouse/Lever + non-job-board research in parallel, finds 50–90 fresh postings, inserts into SQLite DB, saves audit log to `job-data/jobs/`
2. Spawn `job-preparer` — queries the SQLite DB directly (no file argument), scores, ranks, presents top 5 (min score 75) to the user for selection, then prepares tailored resume + cover letter PDFs for user-selected jobs; writes `job-data/output/YYYY-MM-DD/final-report.md` with full URLs

## CV Structure

The YAML follows the RenderCV schema. Key top-level sections under `cv.sections`:

- `summary` — single-paragraph professional identity
- `skills` — label/details pairs (Languages, Cloud and DevOps, AI, Frameworks, Domains)
- `education` — chronological, most recent first
- `experience` — chronological, most recent first; each role has `highlights` (bullet points)
- `publications`, `projects`, `awards` — present if applicable

Keep bullets in `highlights` focused on delivered outcomes, not task descriptions.
