# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## ⛔ STOP — WORK IN A WORKTREE, NEVER ON `main`

**EVERY change to this repository — code, docs, agents, configs, ANYTHING — MUST be made in a git worktree, NEVER directly on `main`.** This is non-negotiable and has no exceptions.

Before editing, creating, or deleting a single file, you MUST first create/enter a worktree (use `EnterWorktree`, or the plan-mode worktree isolation option). Worktrees for this repo live under `.claude/worktrees/`.

If you find yourself about to run `Edit`, `Write`, or any mutating command while on `main`: **STOP.** Create the worktree first, then do the work there. Editing on `main` is a mistake even if the task seems small, even if the user didn't repeat the instruction, and even if you're "just fixing one thing." When in doubt, confirm you are NOT on `main` before your first write.

### Exception: the harness data root is always writable

The worktree rule above applies **only to files inside this repository**. Any harness agent — `job-preparer`, `resume-tailor`, `cover-letter-creator`, and the `job-seeker-*` searchers — is **fully permitted to Read, Write, and Edit anything under `$JOB_DATA_ROOT/**`** (job data, scoring reports, and the prepared resume/cover-letter outputs in `$JOB_DATA_ROOT/output/`). `$JOB_DATA_ROOT` lives **outside** the repository, so it is never on `main` and never needs a worktree. When you are told to write a pipeline artifact to a path under `$JOB_DATA_ROOT` (e.g. an `output_dir`), write it directly — do not stop, do not create a worktree, and do not fall back to `./applications/` inside the repo.

## What This Is

A [RenderCV](https://github.com/rendercv/rendercv)-based resume project. The source of truth is the CV YAML file, validated against the RenderCV v2.8 JSON schema. All outputs (`rendercv_output/`) are generated artifacts — never edit them directly.

## Configuration

Configuration is **data-driven and per-user** (spec 12, phase 1): the values live
in the harness DB and are edited from the TUI/web **Settings** tab or the
`harness-db config` CLI. Only the **bootstrap** pointers needed to find the DB
before a user is known stay in `.claude/settings.local.json` (gitignored — never
committed):

```json
{
  "env": {
    "HARNESS_DB": "/absolute/path/to/job-data/jobs/postings.db",
    "ADZUNA_APP_ID": "**REDACTED**",
    "ADZUNA_API_KEY": "**REDACTED**",
    "JOB_DATA_ROOT": "/absolute/path/to/job-data",
    "RESUME_FILE": "/absolute/path/to/Your_Name_CV.yaml",
    "JOB_TOP_N": "5"
  }
}
```

`HARNESS_DB` locates the SQLite DB directly; if unset it falls back to
`$JOB_DATA_ROOT/jobs/postings.db`. `RESUME_FILE`, `ADZUNA_APP_ID`,
`ADZUNA_API_KEY`, and `JOB_DATA_ROOT` are now **DB config items** resolved via
`harness_db.config_store.get_config(key, uid)` = the active user's stored value →
the env / `settings.local.json` fallback. On first run the harness seeds a
`default` user and **imports** these env values + the legacy config files into it,
so existing single-user setups keep working unchanged; thereafter edit them in
Settings. The active user is resolved CLI flag → `.active-user` dotfile (beside
the DB) → `default`. Agents still read `RESUME_FILE` at runtime via
`bash -c 'echo $RESUME_FILE'` (env fallback).

`JOB_TOP_N` (optional, default `5`) controls how many top-ranked postings `job-preparer`'s `phase: score` returns for the user to pick from. Omit it to keep the default of 5.

The candidate-summary **judgment fields** are also DB config items (spec 14): `CANDIDATE_HEADLINE`, `CANDIDATE_NOTABLE`, `CANDIDATE_YEARS_EXPERIENCE`, `CANDIDATE_WORK_TYPE` (default "fully remote"), `CANDIDATE_ELIGIBILITY` (default "Canada-eligible"), `CANDIDATE_EMPLOYMENT` (csv, default "full-time,contract,freelance"), and `CANDIDATE_COMP_FLOOR_CAD` (optional). Edit them in Settings → Config; on first run they import from an existing `candidate-summary.json`.

### Disqualifiers

The pipeline's hard disqualifiers are **data-driven and per-user**, stored in the DB and edited from Settings → Disqualifiers (or `harness-db disqualifiers …`). They hold both the pre-filter keyword rules (`prefilter`) and the scoring-modifier blocks (`scoring_modifiers`, applied by the scorer during scoring). The `prefilter` is the single **early-disqualification** layer, applied by the `api_search` module (its `run()` for the API sources, and `append` when an MCP searcher merges its batch) so noise never enters the DB — the searcher agents do **not** read or apply the rules themselves. `job-preparer` re-applies it via `harness-db prefilter` to mark any survivors `skipped` before scoring. The loader lives in `harness_db.disqualifiers` (DB-backed, with a legacy `disqualifiers.yaml` file fallback when no DB exists); built-ins seed from `harness-db/harness_db/disqualifiers.default.yaml` and any existing `disqualifiers.yaml` is imported once on first run. Read by `api_search`, `scoring_module`, and `job-preparer`.

Positive search inputs are also DB-driven. The target role titles, title keywords, and domains of interest live per-user in the DB (Settings → Target Roles, or `harness-db target-roles …`); built-ins seed from `harness-db/harness_db/target-roles.default.yaml`. The DB is the source of truth and is read **directly** via the shared `harness_db.target_roles` library. `candidate-summary.json` — the compact profile every searcher reads — is assembled **deterministically** by `harness-db candidate-summary --write` (run in `job-seeker` Step 0): `name`/`location`/`stack` from the resume, `target_titles`/`seniority_keywords`/`domains` from the DB target-roles, and the judgment fields from the `CANDIDATE_*` config keys. It is rewritten only when its inputs change (an `inputs_hash`), so there is no daily LLM synthesis. Exclusions belong in disqualifiers; positive targets in target roles.

### Source selection

Which of the 7 high-level sources run is a **per-user DB selection** (Settings → Sources, or `harness-db sources enable/disable`), read by `job-seeker` via `harness-db sources enabled`. `/job-search` no longer prompts for sources; `--skip`/`--only` remain as transient single-run overrides. The loader is `harness_db.sources_store`.

**`ANTHROPIC_API_KEY` is not required.** The `scoring_module` Python script authenticates by falling back to the OAuth token in `~/.claude/.credentials.json` (the same session Claude Code uses). If you do have an API key, setting it takes priority.

## Rendering

Render the CV to PDF with the **venv's** `rendercv` (pinned in `requirements.txt`, so the harness is self-contained — activate `./venv` first so `rendercv` resolves there, not to a global install):

```bash
. ./venv/bin/activate
rendercv render "$RESUME_FILE"
```

Outputs land in `rendercv_output/` as PDF, HTML, Markdown, Typst, and page images.

## Front-ends

Two UIs sit on top of the shared `harness-db` data layer (`harness_db.queries`,
`harness_db.config`, `harness_db.config_store`, `harness_db.sources_store`,
`harness_db.disqualifiers`, `harness_db.target_roles`, `harness_db.users`,
`harness_db.agent_io`) and stay in sync with the same SQLite DB. Both have a
**Settings** tab (at parity) for the user profile, config values, source
selection, disqualifiers, and target roles — all going through those shared
libraries so neither front-end forks the logic:

- **TUI** (`tui/`) — Textual app. Run with `job-tui`.
- **Web** (`web/`) — Reflex app at TUI parity (browse, sort, detail, status
  changes, Settings, and triggering single-posting scoring/job-preparer with live-streamed output).
  Dev: `cd web && reflex run`. Docker: `docker compose -f web/docker-compose.yml up --build`
  (the lean `web` image plus an `agent-runner` image that isolates the `claude`
  CLI + credentials for in-browser agent runs). See `web/README.md`.

## Agents

The agents are configured in [.claude/agents/](.claude/agents/):

**CV agents:**
- **resume-evaluator** — Runs the CV through achievement reframing, 10-second scan test, and red flag detection. Use via `/resume-work` skill.
- **resume-tailor** — Tailors the CV for a specific job posting (ATS bypass, gap analysis, keyword embedding).
- **cover-letter-creator** — Writes a cover letter from the CV + a job description.

**Job search harness agents** (see `docs/` for the workflow diagram, data flow, database schema, job-state lifecycle, and semantic embeddings):
- **job-seeker** — Orchestrator: spawns the enabled platform searchers (from the DB sources catalog) in parallel, merges results, deduplicates against the SQLite DB, inserts new postings, saves an audit log to `job-data/jobs/search-YYYY-MM-DD.json`.
- **job-seeker-linkedin** — Searches LinkedIn via the LinkedIn MCP server (`mcp__linkedin__search_jobs`).
- **job-seeker-indeed** — Searches Indeed via the Indeed MCP server.

  Each searcher records the hiring companies it saw with one `harness-db companies seen --platform <p> FILE...` call (the per-platform remote/Canada ratchet + notes policy lives in `harness_db.companies`), replacing the per-company SQL the agents used to hand-write.
- **job-seeker-adzuna** — Searches Adzuna Canada via the Adzuna REST API (credentials in `$ADZUNA_APP_ID` / `$ADZUNA_API_KEY`).
- **job-seeker-research** — Finds companies actively hiring via non-LinkedIn/non-Indeed sources (Greenhouse, Lever, Wellfound, funded startups). Acts as a recruitment expert targeting growing and recently funded companies.
- **job-seeker-company** — Researches companies already in the DB and fills in missing intelligence: a careers/jobs-page URL plus notes on how to fetch jobs and job descriptions from that site. Writes findings to the `companies` table and a summary report. Run standalone via the `company-research` skill.
- **job-preparer** — Phase-driven orchestrator (it cannot prompt the user — its questions don't surface from a subagent, so the calling skill owns all user interaction): `phase: score` scores and returns a ranked top-N (count set by the `JOB_TOP_N` env var, default 5); `phase: prepare` (given the user-selected URLs) spawns one `resume-tailor` per selected job in parallel, renders the PDFs, and writes the final report with URLs to `job-data/output/YYYY-MM-DD/final-report.md`; `phase: cover-letters` (given the prepared jobs, only if the user opts in) spawns one `cover-letter-creator` per job and updates the report. Cover letters are off by default.

Scoring is **not** an agent — it is the `scoring_module` Python script (`python -m scoring_module`), which calls the Claude API directly. `job-preparer` runs it on a batch during `/job-search`; the TUI/web "Score" button runs it on a single posting (`--url`). It writes the posting's scores **and** ratchets the hiring company's `remote_confirmed` / `canada_confirmed` / `last_seen_date` flags.

CV agents (`resume-evaluator`, `resume-tailor`, `cover-letter-creator`) use `model: opus`. The orchestrators (`job-seeker`, `job-preparer`) and `job-seeker-research`/`-company` use `model: sonnet`; the deterministic searchers that just run CLI commands and forward output (`job-seeker-adzuna`, `-greenhouse`, `-remotive`) use `model: haiku`, as do the MCP searchers (`-linkedin`, `-indeed`, `-ziprecruiter`).

## General Directives

1. Ask, don't assume. If something is unclear, ask before writing a single line. Never make silent assumptions about intent, architecture, or requirements.

2. Simplest solution first. Always implement the simplest thing that could work. Do not add abstractions or flexibility that weren't explicitly requested.

3. Flag uncertainty explicitly. If you are not confident about an approach or technical detail, say so before proceeding. Confidence without certainty causes more damage than admitting a gap.

## Workflows

**General CV cleanup:** `/resume-work` — spawns the evaluator and applies every suggested edit in one pass, no confirmation prompts.

**Job-specific customization:** Spawn the `resume-tailor` agent with the job description. It will tailor the YAML directly.

**Cover letter:** Spawn the `cover-letter-creator` agent with the job description.

**Full job search run:**
1. Spawn `job-seeker` — searches LinkedIn + Indeed + Adzuna + ZipRecruiter + Greenhouse/Lever + non-job-board research in parallel, finds 50–90 fresh postings, inserts into SQLite DB, saves audit log to `job-data/jobs/`
2. Run the preparation phases via `job-preparer` (driven by the `job-search` skill, which owns all user prompts since the subagent cannot): score & rank → user picks jobs → prepare tailored resume PDFs + `job-data/output/YYYY-MM-DD/final-report.md` with full URLs → ask whether to also generate cover letters (off by default) → optional cover-letter pass

## CV Structure

The YAML follows the RenderCV schema. Key top-level sections under `cv.sections`:

- `summary` — single-paragraph professional identity
- `skills` — label/details pairs (Languages, Cloud and DevOps, AI, Frameworks, Domains)
- `education` — chronological, most recent first
- `experience` — chronological, most recent first; each role has `highlights` (bullet points)
- `publications`, `projects`, `awards` — present if applicable

Keep bullets in `highlights` focused on delivered outcomes, not task descriptions.

<!-- rtk-instructions v2 -->
# RTK (Rust Token Killer) - Token-Optimized Commands

## Golden Rule

**Always prefix commands with `rtk`**. If RTK has a dedicated filter, it uses it. If not, it passes through unchanged. This means RTK is always safe to use.

**Important**: Even in command chains with `&&`, use `rtk`:
```bash
# ❌ Wrong
git add . && git commit -m "msg" && git push

# ✅ Correct
rtk git add . && rtk git commit -m "msg" && rtk git push
```

## RTK Commands by Workflow

### Build & Compile (80-90% savings)
```bash
rtk cargo build         # Cargo build output
rtk cargo check         # Cargo check output
rtk cargo clippy        # Clippy warnings grouped by file (80%)
rtk tsc                 # TypeScript errors grouped by file/code (83%)
rtk lint                # ESLint/Biome violations grouped (84%)
rtk prettier --check    # Files needing format only (70%)
rtk next build          # Next.js build with route metrics (87%)
```

### Test (60-99% savings)
```bash
rtk cargo test          # Cargo test failures only (90%)
rtk go test             # Go test failures only (90%)
rtk jest                # Jest failures only (99.5%)
rtk vitest              # Vitest failures only (99.5%)
rtk playwright test     # Playwright failures only (94%)
rtk pytest              # Python test failures only (90%)
rtk rake test           # Ruby test failures only (90%)
rtk rspec               # RSpec test failures only (60%)
rtk test <cmd>          # Generic test wrapper - failures only
```

### Git (59-80% savings)
```bash
rtk git status          # Compact status
rtk git log             # Compact log (works with all git flags)
rtk git diff            # Compact diff (80%)
rtk git show            # Compact show (80%)
rtk git add             # Ultra-compact confirmations (59%)
rtk git commit          # Ultra-compact confirmations (59%)
rtk git push            # Ultra-compact confirmations
rtk git pull            # Ultra-compact confirmations
rtk git branch          # Compact branch list
rtk git fetch           # Compact fetch
rtk git stash           # Compact stash
rtk git worktree        # Compact worktree
```

Note: Git passthrough works for ALL subcommands, even those not explicitly listed.

### GitHub (26-87% savings)
```bash
rtk gh pr view <num>    # Compact PR view (87%)
rtk gh pr checks        # Compact PR checks (79%)
rtk gh run list         # Compact workflow runs (82%)
rtk gh issue list       # Compact issue list (80%)
rtk gh api              # Compact API responses (26%)
```

### JavaScript/TypeScript Tooling (70-90% savings)
```bash
rtk pnpm list           # Compact dependency tree (70%)
rtk pnpm outdated       # Compact outdated packages (80%)
rtk pnpm install        # Compact install output (90%)
rtk npm run <script>    # Compact npm script output
rtk npx <cmd>           # Compact npx command output
rtk prisma              # Prisma without ASCII art (88%)
```

### Files & Search (60-75% savings)
```bash
rtk ls <path>           # Tree format, compact (65%)
rtk read <file>         # Code reading with filtering (60%)
rtk grep <pattern>      # Search grouped by file (75%). Format flags (-c, -l, -L, -o, -Z) run raw.
rtk find <pattern>      # Find grouped by directory (70%)
```

### Analysis & Debug (70-90% savings)
```bash
rtk err <cmd>           # Filter errors only from any command
rtk log <file>          # Deduplicated logs with counts
rtk json <file>         # JSON structure without values
rtk deps                # Dependency overview
rtk env                 # Environment variables compact
rtk summary <cmd>       # Smart summary of command output
rtk diff                # Ultra-compact diffs
```

### Infrastructure (85% savings)
```bash
rtk docker ps           # Compact container list
rtk docker images       # Compact image list
rtk docker logs <c>     # Deduplicated logs
rtk kubectl get         # Compact resource list
rtk kubectl logs        # Deduplicated pod logs
```

### Network (65-70% savings)
```bash
rtk curl <url>          # Compact HTTP responses (70%)
rtk wget <url>          # Compact download output (65%)
```

### Meta Commands
```bash
rtk gain                # View token savings statistics
rtk gain --history      # View command history with savings
rtk discover            # Analyze Claude Code sessions for missed RTK usage
rtk proxy <cmd>         # Run command without filtering (for debugging)
rtk init                # Add RTK instructions to CLAUDE.md
rtk init --global       # Add RTK to ~/.claude/CLAUDE.md
```

## Token Savings Overview

| Category | Commands | Typical Savings |
|----------|----------|-----------------|
| Tests | vitest, playwright, cargo test | 90-99% |
| Build | next, tsc, lint, prettier | 70-87% |
| Git | status, log, diff, add, commit | 59-80% |
| GitHub | gh pr, gh run, gh issue | 26-87% |
| Package Managers | pnpm, npm, npx | 70-90% |
| Files | ls, read, grep, find | 60-75% |
| Infrastructure | docker, kubectl | 85% |
| Network | curl, wget | 65-70% |

Overall average: **60-90% token reduction** on common development operations.
<!-- /rtk-instructions -->