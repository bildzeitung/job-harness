# Matchwright

Matchwright is an AI harness that finds jobs and tailors your resume and cover
letters to the best matches. Currently, it searches:

* LinkedIn
* Indeed
* Adzuna
* ZipRecruiter
* Greenhouse
* .. and others ..

## Pre-requisites

Software pre-requisites are found in the [Onboarding Guide]((docs/onboarding.md).

**IMPORTANT**: The main input to this tool is a resume developed as a [RenderCV YAML document](https://github.com/rendercv/rendercv). Creating this resume file is beyond the scope of this project, but this machine-readable format is the key document that the AI portions will parse, customize, and use to generate resume and cover letter PDFs.

## Getting started

**Read the setup guide: [`docs/onboarding.md`](docs/onboarding.md)**

This guide includes:

* cloning the repo
* setting up MCP servers
* installing the necessary Python environment
* installing 3rd party tools
* _how to customize your job search_

## Usage

Once everything is configured and ready, invoke the `/job-search` skill in Claude.
This skill runs the harness. During a run, there are some interactive elements:

1. Choose which job sources to exclude from the run (e.g. if **Greenhouse** is not delivering results, then this is how you tell the harness not to search there)

2. Choose which top matches you would like the harness to create a customized resume for

3. Optionally, whether you want the harness to create customized cover letters for the job postings you chose

To browse the collected postings and mark which ones you applied for or rejected, there is a text user interface, `job-tui`, or a **web UI**.
See [the onboarding guide](docs/onboarding.md#10-browse-what-you-collected) on how to run these tools.

## Documentation

* [Onboarding](docs/onboarding.md) — from clone to first run.
* [Database schema](docs/database.md) — the `postings`, `companies`, and vector tables.
* [Job states](docs/job-states.md) — the posting lifecycle.
* [Embeddings](docs/embeddings.md) — the semantic dedup / score-reuse layer.
* [Workflow](docs/harness-workflow.mmd) / [data flow](docs/data-flow.mmd) — agent and data diagrams.
* [CLAUDE.md](CLAUDE.md) — the agent roster, skills, and contributor directives.
