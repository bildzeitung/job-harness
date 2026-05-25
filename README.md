# Job Search Harness

An AI harness that searches for jobs. Currently, it searches:

* LinkedIn
* Indeed
* Adzuna
* ZipRecruiter
* GMail emails from LinkedIn Job Alerts
* .. random sites on the internets ..

## Pre-requisites

* Claude
* Docker
* pyenv

## Setup

* run: `init.sh`

## Configure

Update `.claude/settings.local.json` with:

```json
  "env": {
    "RESUME_FILE": "<path to resume.yaml>",
    "ADZUNA_APP_ID": "<your id>",
    "ADZUNA_API_KEY": "<your key>",
    "JOB_DATA_ROOT": "/<path to>/<job-data>"
  }
```

** Note that this will create a `${JOB_DATA_ROOT}/jobs/postings.db` SQLite DB

## Usage

### Agents

The top-line is: `/job-search`. This runs the full harness and allows for job listing source selection.

Additionally,

```bash
. ./venv/bin/activate && job-tui
```

will invoke a text user interface that will show you the current state of the job posting database.
