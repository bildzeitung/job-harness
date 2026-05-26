# Job Harness Laundry List

Important: **Use the AskUserQuestion tool if you have uncertainty about this description**

## Work Items

Work through each of the following subsections. Each subsection is a different module.

### tui

- [ ] the app exits on a `prepare`. Analyze the app and have this spawn asynchronously instead. I should be able to review the output of the job once it's done in a window.

### scoring-module

- [ ] scoring-module: Refactor to use Typer in `__main__.py`; it's tidier.
- [ ] `scorer.py` hardcodes `/home/dmklein/mcp-sqlite/job-search.db`; remove the default -- it's a hard failure if no DB path is available
- [ ] The candidate profile part of `_SYSTEM_PROMPT` should be retrieved from `candidate_profile.json`, not hard coded.
- [ ] Put the contents of `_SYSTEM_PROMPT` into its own file; I would like to churn the prompt without going into the code. This means that the candidate profile has some placeholder where it should be inserted, e.g. `{{CANDIDATE_PROFILE}}`
- [ ] in the function `_score_one()`, should there be some sort of notice that the job description pulled was too large? Grabbing the job description at this point seems prone to issues, since there are a number significant number of variations on where in an HTML doc or API the description appears. Can we make the job description an invariant and ensure the scorer always has it? Check the job-seeker agents for this.
- [ ] `scorer.py` makes DB changes. The tui module uses SQLAlchemy, and this module should, too. Refactor across all DB-using Python modules with common database code.
- [ ] `score_batch()` issues a warning that data won't be saved if there is no `JOB_DATA_ROOT`. This is actually a hard fail, so check it up front. Do not do work if you can't save it!
- [ ] In `score_batch()`, put the max number of ThreadPoolExecutor workers as a constant at the top of the file (e.g. like `JOB_DATA_ROOT`). Write a memory that for Python code, *all* constants should be called out at the top of the module file as constants. There should be no bare numbers in the code.
