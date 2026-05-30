---
name: job-search
description: Run the full job search harness — seek fresh postings, score them, and prepare tailored resumes for the top matches (cover letters optional, offered at the end).
allowed-tools: Read, Write, Bash, Agent(job-seeker, job-preparer)
---

Run the complete job search pipeline.

## Step 0: Determine Active Sources

The 6 available sources are: `linkedin`, `indeed`, `adzuna`, `ziprecruiter`, `greenhouse`, `research`

**If args were provided with the skill invocation:**
- `--skip=<csv>` → disable those sources, run all others (e.g. `--skip=research`)
- `--only=<csv>` → run only those sources, disable all others (e.g. `--only=linkedin,adzuna`)
- Compute `enabled_sources` from the args and skip to writing the config file below.

**If no args were provided:** ask the user, in plain text, which sources to **skip** as a comma-separated list. Do **not** use AskUserQuestion. Wait for the reply before continuing. An empty reply (or "none") means run all 6.

Ask:

> Which sources should be skipped this run? Reply with a comma-separated list, or leave empty / say "none" to run all.
> Available: `linkedin` (MCP, needs active browser session), `indeed` (MCP), `adzuna` (REST API), `ziprecruiter` (MCP), `greenhouse` (Greenhouse.io + Lever.co public APIs), `research` (non-job-board: Wellfound, Ashby, funded startups, niche boards).

Parse the reply: split on commas, trim whitespace, lowercase, and keep only values matching the 6 known source names (ignore anything unrecognized). Compute `enabled_sources` as all 6 minus the parsed skip list.

**Write the config file:**

Run `bash -c 'echo $JOB_DATA_ROOT'` to get the data directory. Write `$JOB_DATA_ROOT/jobs/sources-config.json`:

```json
{"enabled": ["linkedin", "indeed", "adzuna", "ziprecruiter", "greenhouse", "research"]}
```

Replace the array with the actual `enabled_sources` list.

## Steps 1–3

1. Spawn the `job-seeker` agent (subagent_type: job-seeker). It reads `sources-config.json` to know which sources are active, searches those sources in parallel for remote, Canada-eligible senior roles, deduplicates against the SQLite DB, inserts new postings, and saves an audit log to `job-data/jobs/search-YYYY-MM-DD.json`. Wait for it to complete.

2. Spawn the `job-preparer` agent (subagent_type: job-preparer). It queries the SQLite DB directly for new postings — no file argument needed. It will score every posting in parallel, present the top 5 (min score 75) to the user for selection, then produce a tailored resume and PDF for each user-selected job under `job-data/output/YYYY-MM-DD/`. After writing the final report it asks once whether to generate cover letters (off by default); if the user opts in it runs a follow-up cover-letter pass. Wait for it to complete.

3. Report the final summary table that `job-preparer` produces, including rank, company, title, score, and status for each prepared application.
