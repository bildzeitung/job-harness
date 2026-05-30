---
name: job-search-email
description: Run the job search pipeline using ONLY the Gmail job alert email — skips LinkedIn, Indeed, Adzuna, and research sources.
allowed-tools: Read, Write, Bash, Agent, ToolSearch
---

Run the email-only job search pipeline.

Steps:

1. **Check Gmail MCP availability.** Use ToolSearch with `query: "+gmail search_threads"`. If no results are returned, stop and tell the user the Gmail MCP is unavailable — they should check their MCP configuration and ensure the server is running.

2. **Spawn the `job-seeker-email` agent** (subagent_type: job-seeker-email). It will read the most recent LinkedIn job alert email from Gmail, extract job postings, label the email with `AI`, save results to `job-data/jobs/email-{YYYY-MM-DD}.json`, and insert new postings into the SQLite DB. Wait for it to complete.

3. **Prepare via `job-preparer`, in phases.** `job-preparer` cannot prompt the user (it runs as a subagent and its questions do not surface), so **you** own every user decision — ask in **plain text**, never `AskUserQuestion`. Run the same phased flow as the `job-search` skill:
   - Spawn `job-preparer` with `phase: score`; it returns a ranked top-5 table with URLs.
   - Present the table and ask the user which rank numbers to prepare (or `none`); map ranks → URLs. Stop if `none`.
   - Spawn `job-preparer` with `phase: prepare` and `selected_urls`; it prepares resumes + PDFs under `job-data/output/YYYY-MM-DD/`, writes `final-report.md`, and returns a `prepared_jobs` handoff.
   - Ask whether to generate cover letters (off by default). If the user opts in, spawn `job-preparer` with `phase: cover-letters` and `prepared_jobs`; it generates the cover letters and updates the report.

4. **Report** the final summary table (rank, company, title, score, status, and whether cover letters were generated), plus the path to `final-report.md`.
