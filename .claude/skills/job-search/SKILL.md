---
name: job-search
description: Run the full job search harness — seek fresh postings, score them, and prepare tailored resumes and cover letters for the top matches.
allowed-tools: Read, Write, Bash, Agent(job-seeker, job-preparer)
---

Run the complete job search pipeline.

Steps:

1. Spawn the `job-seeker` agent (subagent_type: job-seeker). It will search LinkedIn, Indeed, Adzuna, ZipRecruiter, Greenhouse/Lever, Gmail alerts, and non-job-board sources in parallel for remote, Canada-eligible senior roles, deduplicate against the SQLite DB, insert new postings, and save an audit log to `job-data/jobs/search-YYYY-MM-DD.json`. Wait for it to complete.

2. Spawn the `job-preparer` agent (subagent_type: job-preparer). It queries the SQLite DB directly for new postings — no file argument needed. It will score every posting in parallel, select the top 5 (min score 75), then produce a tailored resume, cover letter, and PDF for each selected job under `job-data/output/YYYY-MM-DD/`. Wait for it to complete.

3. Report the final summary table that `job-preparer` produces, including rank, company, title, score, and status for each prepared application.
