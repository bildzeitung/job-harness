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

## Steps 1–5

> **`job-preparer` cannot prompt the user** — it runs as a subagent and its questions do not surface. **You** (the main agent running this skill) own every user decision. `job-preparer` runs in phases and returns control to you between them. Ask the user in **plain text** (no `AskUserQuestion`), matching the Step 0 style above.

1. **Search.** Spawn the `job-seeker` agent (subagent_type: job-seeker). It reads `sources-config.json` to know which sources are active, searches those sources in parallel for remote, Canada-eligible senior roles, deduplicates against the SQLite DB, inserts new postings, and saves an audit log to `job-data/jobs/search-YYYY-MM-DD.json`. Wait for it to complete.

2. **Score & rank.** Spawn `job-preparer` with `phase: score`. It scores every new/stale posting in parallel and returns a ranked top-5 table — scoped to the **current batch** (the most recent scoring date), not all-time — that includes each job's URL. Wait for it to complete.

3. **Ask which jobs to prepare.** Present the ranked table to the user (you may drop the URL column for readability). Then ask, in plain text:

   > Reply with the rank numbers of the jobs to prepare (e.g. `1 3` or `1, 2, 4`), or `none` to stop.

   Wait for the reply. Parse space/comma-separated integers; map each rank back to its URL using the table from step 2. If the reply is `none` or contains no valid ranks, stop here — the run is complete.

4. **Prepare resumes.** Spawn `job-preparer` with `phase: prepare` and `selected_urls: [<the chosen URLs>]`. It marks them selected, prepares a tailored resume + PDF for each under `job-data/output/YYYY-MM-DD/`, writes `final-report.md` (cover letters shown as "not generated"), and returns a `prepared_jobs` handoff (company, url, output_dir, resume_yaml_path per job). Wait for it to complete.

5. **Offer cover letters, then optionally generate them.** Cover letters are **off by default**. Ask the user, in plain text:

   > Resumes are prepared and the final report is written. Generate cover letters too? Reply `yes` to generate them (or name specific companies), or `no` to finish.

   Wait for the reply.
   - If `no` / empty / no clear affirmative: stop — report the summary from step 4.
   - If affirmative: spawn `job-preparer` with `phase: cover-letters` and `prepared_jobs: [<the handoff from step 4, filtered to any companies the user named>]`. It generates the cover letters, updates `final-report.md`, and returns a summary. Wait for it to complete.

Finally, report the summary table (rank, company, title, score, status) including whether cover letters were generated, and the path to `final-report.md`.
