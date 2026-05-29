# Job Search Harness

An AI harness that searches for jobs. Currently, it searches:

* LinkedIn
* Indeed
* Adzuna
* ZipRecruiter
* Greenhouse
* GMail emails from LinkedIn Job Alerts
* .. random sites on the internets ..

## Pre-requisites

* Claude
* Docker
* pyenv

## Setup

* run: `init.sh`
* also, `mkdir ~/job-data` (this is your job search directory)

## Configure

There is some local configuration required.

Update `.claude/settings.local.json` with:

```json
  "env": {
    "RESUME_FILE": "<full path to resume.yaml>",
    "ADZUNA_APP_ID": "<your id>",
    "ADZUNA_API_KEY": "<your key>",
    "JOB_DATA_ROOT": "/<your path to>/job-data"
  }
```

** Note that this will create a `${JOB_DATA_ROOT}/jobs/postings.db` SQLite DB

## Usage

### Your Resume

The input YAML resume that this harness expects is in [RenderCV format](https://github.com/rendercv/rendercv).
This tool does a create job of creating a formatted resume so that you can
concentrate on the content instead. Once you have created your YAML resume, you
can use this harness. 

### Agents

The top-line is: `/job-search`. This runs the full harness and allows for job listing source selection.

### Job Database UI

You may want to explore the collected data yourself. For that, there is a TUI:

```bash
. ./venv/bin/activate && job-tui
```

This application presents a list of job postings that the harness has
collected, along with their status. Pressing `Enter` opens an expanded
window that displays additional details.

### Job Database Web UI

A web app version of the text UI is available in the `./web` directory. One workflow: 

```bash
; cd ./web
; ./build-images.sh
; export JOB_DATA_ROOT=/path/to/job-data
; docker-compose -f web/docker-compose.yml up --build
```

