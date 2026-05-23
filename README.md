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
    "RESUME_FILE": "<path to resume.yaml",
    "ADZUNA_APP_ID": "<your id>",
    "ADZUNA_API_KEY": "<your key>",
    "JOB_DATA_ROOT": "/<path to>/<job-data>"
  }
```
