---
name: job-search-email
description: Run the job search pipeline using ONLY the Gmail job alert email — skips LinkedIn, Indeed, Adzuna, and research sources.
allowed-tools: Read, Write, Bash, Agent, ToolSearch
---

Run the email-only job search pipeline.

Steps:

1. **Check Gmail MCP availability.** Use ToolSearch with `query: "+gmail search_threads"`. If no results are returned, stop and tell the user the Gmail MCP is unavailable — they should check their MCP configuration and ensure the server is running.

2. **Spawn the `job-seeker-email` agent** (subagent_type: job-seeker-email). It will read the most recent LinkedIn job alert email from Gmail, extract job postings, label the email with `AI`, save results to `job-data/jobs/email-{YYYY-MM-DD}.json`, and insert new postings into the SQLite DB. Wait for it to complete.

3. **Spawn the `job-preparer` agent** (subagent_type: job-preparer). It queries the SQLite DB directly for new postings — no file argument needed. It will score every posting, select the top 5 (min score 75), then produce a tailored resume and PDF for each selected job under `job-data/output/YYYY-MM-DD/`. After writing the final report it asks once whether to generate cover letters (off by default); if the user opts in it runs a follow-up cover-letter pass. Wait for it to complete.

4. **Report** the final summary table that `job-preparer` produces, including rank, company, title, score, and status for each prepared application.
