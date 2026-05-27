---
name: company-research
description: Research companies in the harness DB that are missing a careers/jobs URL or fetch notes, and fill them in. Spawns the job-seeker-company agent.
allowed-tools: Read, Write, Bash, Agent, ToolSearch
---

Enrich company records in the job-harness database with careers-page intelligence.

Steps:

1. **Spawn the `job-seeker-company` agent** (subagent_type: job-seeker-company). It queries the `companies` table for rows missing `careers_url` or `fetch_notes`, finds at least one careers/jobs URL per company plus notes on how to fetch jobs and job descriptions from that site, writes the findings back to the DB, and saves a summary report to `job-data/jobs/reports/company-research-{YYYY-MM-DD}.md`. Wait for it to complete.

2. **Report** the agent's summary: how many companies were researched, how many were resolved (URL found) vs. unresolved (with the reason), and the path to the report file.
