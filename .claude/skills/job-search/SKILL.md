---
name: job-search
description: Run the full job search harness — seek fresh postings, score them, and prepare tailored resumes for the top matches (cover letters optional, offered at the end).
allowed-tools: Read, Write, Bash, Agent(job-seeker, job-preparer)
---

Run the complete job search pipeline.

## Step 0: Determine Active Sources

Source selection is **data-driven and per-user** — it lives in the harness DB and
the user manages it from the TUI/web **Settings → Sources** panel. **Do not prompt
the user about sources**, and do not write any config file. The `job-seeker` agent
reads the enabled set directly from the DB (`harness-db sources enabled`).

The 7 available sources are: `linkedin`, `indeed`, `adzuna`, `ziprecruiter`, `greenhouse`, `remotive`, `research`

**Optional transient override (args only):** if the skill was invoked with args,
treat them as a one-run override that does **not** change the stored selection:
- `--skip=<csv>` → run all enabled sources except these (e.g. `--skip=research`)
- `--only=<csv>` → run only these (e.g. `--only=linkedin,adzuna`)

To apply an override: run `harness-db sources enabled` to get the stored set, then
split on commas / trim / lowercase the arg and subtract (`--skip`) or intersect
(`--only`), and pass the resulting `enabled_sources` list to `job-seeker` in its
spawn prompt. With no args, spawn `job-seeker` with no source override — it reads
the DB itself.

## Steps 1–5

> **`job-preparer` cannot prompt the user** — it runs as a subagent and its questions do not surface. **You** (the main agent running this skill) own every user decision. `job-preparer` runs in phases and returns control to you between them. Ask the user in **plain text** (no `AskUserQuestion`), matching the Step 0 style above.

1. **Search.** Spawn the `job-seeker` agent (subagent_type: job-seeker). It reads the enabled sources from the DB (`harness-db sources enabled`) — or uses the transient `enabled_sources` override if you computed one in Step 0 — searches those sources in parallel for remote, Canada-eligible senior roles, deduplicates against the SQLite DB, inserts new postings, and saves an audit log to `job-data/jobs/search-YYYY-MM-DD.json`. Wait for it to complete.

   **Present the detailed search report.** `job-seeker` returns a detailed report (also written to `job-data/jobs/search-report-YYYY-MM-DD.md`) with three sections: (1) every source and the number of positions found in each, (2) any content-fetch problems, and (3) any other execution issues. Show this report to the user verbatim before moving on to scoring — do not summarize it away. If the agent's reply did not include the report, read it from `$JOB_DATA_ROOT/jobs/search-report-YYYY-MM-DD.md` and present that.

2. **Score & rank.** Spawn `job-preparer` with `phase: score`. It scores every new/stale posting in parallel and returns a ranked top-N table (N is set by the `JOB_TOP_N` env var, default 5) — scoped to the **current batch** (the most recent scoring date), not all-time — that includes each job's URL. Wait for it to complete.

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
