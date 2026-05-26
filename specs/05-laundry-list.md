# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about this description**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### harness-db

- [ ] add a mapping for the `companies` table (relates to tui feature add below)

### tui

- [ ] allow the user to choose which column to sort by; use must be able to use the keyboard to choose the sort column
- [ ] by default, jobs should be listed by state, then date, then job title
- [ ] states are ordered as follows: selected, scored, new, applied, skipped
- [ ] i want to explore the `companies` in the database too; provide a tab or way to switch views so that i can see a table showing the contents of `companies`

### agents

- [ ] the job database lists jobs in the `new` state; i need a way to run the harness so that these are either scored or skipped; this possibly relates to the next item where jobs seem to stay "new".
- [ ] in `docs/job-states.md` the diagram states "soft skill mismatch (excluded this run, re-evaluated next)". Does this really happen? Identify this case and fix it such that we do not stay in "new".

### docs

- [ ] Mermaid diagrams do not understand `\n`. Use `<br>` instead to split text into multiple lines.

### scoring-module

- [ ] BUG: in `_load_system_prompt()`, the `candidate_profile.json` is actually `candidate_summary.json` and should be read from `$JOB_DATA_ROOT/candidate_summary.json`. Delete the candidate_profile.json file from the source tree.

### all Python modules

- [ ] add a memory so that running tests is done by invoking the venv and calling pytest. e.g. `. <path to>/venv/bin/activate && pytest` The tools seem to look for `pytest` repeatedly.
- [ ] add `nox` as a dev dependency
- [ ] add the `noxfile.py` below to every module
- [ ] add a memory so that *before code is merged* a `. <path to>/venv/bin/activate && nox -t fix` *must* be run for the module. This is a code lint and formatting tool. Any errors must be fixed. If the git tree is dirty, commit the changes before merge.
- [ ] add the `ruff` config below to each `pyproject.toml` file

## Files

### noxfile.py

```python
import nox

nox.options.default_venv_backend = "uv"

@nox.session(tags=["style", "fix"])
def ruff_format(session):
    session.install("ruff")
    session.run("ruff", "format")
    session.run("ruff", "check", "--fix")
```

### ruff config

```python
[tool.ruff]
line-length = 100
lint.extend-select = ["I"]
```
