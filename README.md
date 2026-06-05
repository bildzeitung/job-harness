# Job Search Harness

An AI harness that searches for jobs. Currently, it searches:

* LinkedIn
* Indeed
* Adzuna
* ZipRecruiter
* Greenhouse
* .. random sites on the internets ..

## Pre-requisites

* Claude
* Docker
* pyenv

## Getting started

**[`docs/onboarding.md`](docs/onboarding.md) is the setup guide** — it walks you
from a fresh clone to your first `/job-search` run: the Python sqlite-extension
prerequisite, `init.sh` / `3rdparty-install.sh`, creating a [RenderCV-format](https://github.com/rendercv/rendercv)
resume YAML, configuring `.claude/settings.local.json`, connecting the MCP
servers, and browsing results.

## Usage

Once you're set up, the top-line is `/job-search` — it runs the full harness and
lets you pick which job sources to search. To browse the collected postings
yourself, there's a Textual **TUI** (`job-tui`) and a Reflex **web UI** (`./web`,
at TUI parity). See [the onboarding guide](docs/onboarding.md#10-browse-what-you-collected)
for how to run each.

## Documentation

* [Onboarding](docs/onboarding.md) — from clone to first run.
* [Database schema](docs/database.md) — the `postings`, `companies`, and vector tables.
* [Job states](docs/job-states.md) — the posting lifecycle.
* [Embeddings](docs/embeddings.md) — the semantic dedup / score-reuse layer.
* [Workflow](docs/harness-workflow.mmd) / [data flow](docs/data-flow.mmd) — agent and data diagrams.
* [CLAUDE.md](CLAUDE.md) — the agent roster, skills, and contributor directives.
