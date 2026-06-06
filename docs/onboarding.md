# Onboarding — from clone to your first job search

This guide will take you from a fresh `git clone` to a first
successful `/job-search` run with your resume.

By the end you will have:

- a Python venv with the harness installed,
- the local embedding model running,
- your own RenderCV resume YAML,
- the harness configured to find it,
- the MCP servers connected, and
- a populated `postings.db` you can browse in the TUI or web UI.

> **Read alongside:** the [README](../README.md) is the terse overview; this is
> the narrated version with the *why* and the first-time gotchas. The deeper
> reference docs ([database](database.md), [job states](job-states.md),
> [embeddings](embeddings.md), and the workflow/data-flow diagrams) are linked
> where relevant.

---

## 1. Prerequisites

Install these before cloning the repo:

| Tool | Why | Notes |
|------|-----|-------|
| **Claude Code** | The harness *is* a set of Claude Code agents and skills. There is no standalone binary. | This is the thing you run `/job-search` in. |
| **Docker** | The SQLite and LinkedIn MCP servers run as containers. | On WSL the launcher scripts call `wsl.exe docker …` — see [§6](#6-connect-the-mcp-servers). |
| **pyenv** | Pins Python to the exact version the venv is built against. | Version is in [`.python-version`](../.python-version). |
| **Adzuna API account** | Free Adzuna app credentials power the Adzuna Canada search source. | Sign up at <https://developer.adzuna.com/>. Optional but recommended. |

---

## 2. Clone and pick the right Python

```bash
git clone git@github.com:bildzeitung/job-harness.git job-harness
cd job-harness
```

The harness's semantic dedup/similarity layer uses
[sqlite-vec](https://github.com/asg017/sqlite-vec), a loadable SQLite extension.
**Your Python must have been built with loadable-extension support** — the stock **pyenv** especially may not! Check:

```bash
python -c 'import sqlite3; print(hasattr(sqlite3.connect(":memory:"), "enable_load_extension"))'
```

If that does not print `True`, rebuild the pinned Python with the flag turned on:

```bash
PYTHON_CONFIGURE_OPTS="${PYTHON_CONFIGURE_OPTS} --enable-loadable-sqlite-extensions" \
  pyenv install --force "$(cat .python-version)"
```

`init.sh` (next step) re-runs this same check and stops with guidance if it
still fails.

---

## 3. Build the Python environment

```bash
./init.sh
```

This creates `./venv/` and installs everything in [`requirements.txt`](../requirements.txt):
RenderCV plus the editable harness packages (`harness-db`, `scoring-module`,
`consolidate-module`, `api-search`, `tui`, `web`) and the LinkedIn MCP package.

> The venv lives at the **repo root** (`./venv/`), not inside any module
> subdirectory. Activate it with `. ./venv/bin/activate` whenever you run a
> harness command directly (the TUI, backfills, tests).

---

## 4. Install the third-party tools

```bash
./3rdparty-install.sh
```

This installs:

- **[RTK](https://github.com/rtk-ai/rtk)** — the token-optimizing CLI proxy.
- **[Ollama](https://ollama.com)** and the **`qwen3-embedding:0.6b`** model — the
  local, on-GPU embedding model that powers semantic repost-dedup and score
  reuse. No API calls, no tokens. See [embeddings.md](embeddings.md) for what it
  does and how to tune it.

Then create your job-data directory — everything the harness produces (the
database, scoring reports, tailored resumes) lives here, **outside** the repo:

```bash
mkdir ~/job-data
```

---

## 5. Create your resume YAML

This is the step the other docs assume you already did. The harness's single
source of truth about *you* is one [RenderCV](https://github.com/rendercv/rendercv)-format
YAML file. Everything downstream — the search keywords, the fit scores, the
tailored resumes — is derived from it.

You have two ways to scaffold one:

- **Use the `/rendercv` skill** inside Claude Code and describe your background;
  it will build and render a valid YAML for you. *(Recommended — it knows the
  v2.8 schema.)*
- **Scaffold by hand** with RenderCV's generator, then edit:

  ```bash
  . ./venv/bin/activate
  rendercv new "Your Full Name"
  ```

Either way, fill in the standard sections under `cv.sections` — `summary`,
`skills`, `education`, `experience` (with outcome-focused `highlights`), and
optionally `publications`, `projects`, `awards`. The [CLAUDE.md "CV Structure"
section](../CLAUDE.md) describes what each section is for.

Render it to confirm it is valid:

```bash
rendercv render /path/to/Your_Name_CV.yaml
```

Outputs land in `rendercv_output/` (PDF, HTML, Markdown, Typst, images). Those
are **generated artifacts** — never edit them by hand; always edit the YAML.

Put the YAML wherever you like (a common choice is alongside the repo or in a
personal resume folder); you will point the harness at its absolute path next.

---

## 6. Configure the harness

All per-user configuration is environment variables in
`.claude/settings.local.json`. **This file is gitignored — never commit it.**
Create it if it does not exist:

```json
{
  "env": {
    "RESUME_FILE": "/absolute/path/to/Your_Name_CV.yaml",
    "JOB_DATA_ROOT": "/home/you/job-data",
    "ADZUNA_APP_ID": "your-adzuna-app-id",
    "ADZUNA_API_KEY": "your-adzuna-api-key",
    "JOB_TOP_N": "5"
  }
}
```

| Variable | What it does |
|----------|--------------|
| `RESUME_FILE` | Absolute path to the YAML from [§5](#5-create-your-resume-yaml). Agents read it at runtime; this is what makes the harness shareable. |
| `JOB_DATA_ROOT` | Your job-data directory. The database lands at `$JOB_DATA_ROOT/jobs/postings.db`; tailored output at `$JOB_DATA_ROOT/output/`. |
| `ADZUNA_APP_ID` / `ADZUNA_API_KEY` | Adzuna Canada API credentials. Needed only for the Adzuna search source. |
| `JOB_TOP_N` | Optional. How many top-ranked postings `/job-search` presents for you to choose from. Defaults to `5` if unset. |

> **No `ANTHROPIC_API_KEY` required.** The scoring module authenticates by
> falling back to the OAuth token in `~/.claude/.credentials.json` — the same
> session Claude Code already uses. Setting an API key takes priority if you
> have one, but it is optional.

---

## 7. Connect the MCP servers

The harness talks to LinkedIn and to the SQLite database through MCP servers
declared in [`.mcp.json`](../.mcp.json). Both run in Docker via launcher scripts
in [`scripts/`](../scripts/). The shipped scripts invoke `wsl.exe docker …`
because they were written for Docker-on-Windows under WSL — **if you are on
native Linux or macOS, edit `scripts/linkedin-mcp.sh` and `scripts/sqlite-mcp.sh`
to call `docker` directly** (drop the `wsl.exe` prefix).

- **SQLite MCP** (`scripts/sqlite-mcp.sh`) — mounts `$JOB_DATA_ROOT/jobs` into a
  `mcp/sqlite` container pointed at `postings.db`. It fails fast if
  `JOB_DATA_ROOT` is unset, so make sure [§6](#6-configure-the-harness) is done.
  No manual login needed.

- **LinkedIn MCP** (`scripts/linkedin-mcp.sh`) — runs the
  `stickerdaniel/linkedin-mcp-server` container against a session stored in
  `~/.linkedin-mcp`. The first time, log in to seed that session:

  ```bash
  ./scripts/login-linkedin.sh
  ```

LinkedIn, Indeed, and ZipRecruiter sources are **probed for connectivity** at
search time and skipped if unavailable — so you can do a useful first run with
just the always-on sources (Adzuna, Greenhouse/Lever, and web research) even
before LinkedIn is wired up.

---

## 8. (Optional) Tune your search config

Two user-editable files in `$JOB_DATA_ROOT` steer the search. You do **not** have
to create either — the first run seeds each from a shipped template if it is
missing, and never overwrites a copy you have tuned. They are complementary:
`target-roles.md` says what to **look for**, `disqualifiers.yaml` says what to
**drop**.

### Target roles — what to look for

`$JOB_DATA_ROOT/target-roles.md` is the canonical list of **positive targets**:
the role titles, the title keywords that drive search queries and seniority
filtering, and your domains of interest. Every `job-seeker` searcher reads it,
and it feeds the generated `candidate-summary.json` (the rest of which — name,
headline, stack, location — comes from your resume YAML). Seeded from
[`harness-db/harness_db/target-roles.default.md`](../harness-db/harness_db/target-roles.default.md)
(a senior-engineering starter) — edit the **Title Keywords** and **Domains**
sections to match the roles you actually want.

### Disqualifiers — what to drop

`$JOB_DATA_ROOT/disqualifiers.yaml` holds the hard **exclusions**, seeded from
[`harness-db/harness_db/disqualifiers.default.yaml`](../harness-db/harness_db/disqualifiers.default.yaml).
It has two independent parts:

- **`prefilter`** — postings whose title/summary match these phrases are dropped
  before scoring (and at search time), marked `skipped`. Defaults exclude
  US-only authorization, mandatory relocation, etc.
- **`scoring_modifiers`** — negative score adjustments the scorer applies *during*
  scoring (e.g. requires a named certification → −40).

This is the **single source of truth** for exclusions, read by the searchers,
the scorer, and `job-preparer`. Edit it to tune behavior; see
[job-states.md](job-states.md) and [database.md](database.md) for how the two
mechanisms differ.

---

## 9. Your first run

Inside Claude Code, run:

```
/job-search
```

This drives the full harness (see the [workflow diagram](harness-workflow.mmd)
and [data-flow diagram](data-flow.mmd)):

1. **Seek** — `job-seeker` derives search terms from your resume, lets you pick
   which sources to enable, searches them in parallel, deduplicates (by URL and
   by semantic similarity), and inserts new postings as `status = new`. An audit
   log is saved to `$JOB_DATA_ROOT/jobs/search-YYYY-MM-DD.json`.
2. **Score** — postings are pre-filtered against your disqualifiers, then scored
   1–100 across five dimensions with age/competition modifiers.
3. **Select** — you are shown the ranked top matches and choose which to prepare.
4. **Prepare** — for each chosen job, `resume-tailor` produces an ATS-targeted
   resume and renders a PDF. You are then asked whether to also generate cover
   letters (**off by default**).

Outputs land in `$JOB_DATA_ROOT/output/YYYY-MM-DD/`: a `final-report.md` (ranked
list with company, title, score, URL, and status) plus the tailored resume PDFs
(and cover letters, if you opted in).

The skill — not the agents — owns every user prompt, because subagents cannot
ask you questions. So all the "which sources?", "which jobs?", "cover letters?"
decisions surface in your `/job-search` conversation.

---

## 10. Browse what you collected

You don't have to drive everything through `/job-search`. Two UIs sit on the
same `postings.db`:

**TUI** (Textual):

```bash
. ./venv/bin/activate && job-tui
```

A sortable list of postings with status; press `Enter` for detail, `a` to mark
applied, `x` to reject. The full lifecycle is in [job-states.md](job-states.md).

**Web UI** (Reflex, at TUI parity — browse, sort, detail, status changes, and
triggering the scorer/preparer with live-streamed output):

```bash
cd web
./build-images.sh
export JOB_DATA_ROOT=/path/to/job-data
docker compose -f docker-compose.yml up --build
```

See [`web/README.md`](../web/README.md) for details.

---

## 11. Verification checklist

Work through this if a first run misbehaves:

- [ ] `python -c 'import sqlite3; print(hasattr(sqlite3.connect(":memory:"),"enable_load_extension"))'` prints `True`.
- [ ] `. ./venv/bin/activate` succeeds and `job-tui` is on `PATH`.
- [ ] `ollama list` shows `qwen3-embedding:0.6b`.
- [ ] `echo $RESUME_FILE` (from inside Claude Code) prints your YAML's absolute path, and the file exists.
- [ ] `rendercv render "$RESUME_FILE"` produces a PDF without schema errors.
- [ ] `echo $JOB_DATA_ROOT` is set and the directory exists.
- [ ] After `/job-search`, `$JOB_DATA_ROOT/jobs/postings.db` exists and the TUI lists postings.
- [ ] (If using LinkedIn) `./scripts/login-linkedin.sh` completed and `~/.linkedin-mcp` has a session.

---

## Where to go next

- **[database.md](database.md)** — the schema: `postings`, `companies`, `company_postings`, and the `postings_vec` sidecar.
- **[job-states.md](job-states.md)** — the posting lifecycle (`new → scored → selected → prepared → applied`) and who sets each state.
- **[embeddings.md](embeddings.md)** — the semantic dedup/score-reuse layer and its tuning knobs.
- **[harness-workflow.mmd](harness-workflow.mmd)** / **[data-flow.mmd](data-flow.mmd)** — the full agent and data-flow diagrams.
- **[CLAUDE.md](../CLAUDE.md)** — the agent roster, skills, and contributor directives.
</content>
</invoke>
