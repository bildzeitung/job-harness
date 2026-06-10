# Spec 14 — Robustness & Token Optimisation

Important: **Use the AskUserQuestion tool if you have uncertainty about the tasks; confidence level >=95%.** Decisions already made by the user are listed below — do not re-ask them.

## Goal

Make the harness more reliable and resistant to drift/hallucination, and cut token
spend, by (a) moving every behavior an LLM currently "applies by eyeball" into the
tested Python modules, (b) bringing the agent prompt files back in sync with the
code they describe, and (c) trimming prompt/tool overhead that is paid on every
spawn.

The guiding principle for every item: **wherever an agent prompt describes
behavior that also exists in code (schema, filter rules, file formats, pipeline
shape), the prompt must be reduced to "run this command, report its output."**
Prose duplicates of code are drift points that eventually become hallucinations.

## Decisions already made (do not re-ask)

| Topic | Decision |
|-------|----------|
| MCP probe failure (job-seeker Step 1) | **Keep the hard stop.** An unavailable enabled source still aborts the run. Document that this is deliberate so a future pass doesn't "fix" it. |
| candidate-summary judgment fields | **DB config via Settings.** `headline`, `notable`, `years_experience`, and the requirements fields become per-user config keys; a deterministic CLI assembles the JSON. No daily LLM synthesis. |
| resume-tailor fetching | **job-preparer always supplies `job_description_text`** in pipeline mode (fetching it itself if the DB field is empty). resume-tailor additionally gets `WebFetch` for interactive use only. |
| Prefilter scope in `api_search append` | Apply **only** `prefilter_disqualifies` to appended batches — NOT `is_remote`/`is_senior`. MCP searchers verify remote/seniority with full-context judgment; mechanical keyword checks on snippet-only postings (e.g. research) would silently drop verified results. |

## Process rules

- **Every change in a git worktree under `.claude/worktrees/`, branched from local `main` HEAD** — never on `main`, never from `origin/main`.
- One commit per work item (granular history).
- For each Python module touched: `. <module>/venv/bin/activate && nox -t fix` and `nox -s tests` must pass before merging.
- Docs: "update the docs" means **all** files in `docs/*` are in scope. Validate Mermaid diagrams with `nox -s docs_mermaid` (root noxfile, Docker). Use `<br>` not `\n` for Mermaid line breaks.
- New CLI surfaces use **Typer** (never argparse), except inside `api_search` whose existing `__main__` is hand-rolled — extend its existing style there.
- Keep `BUILTIN_SOURCES` in `harness-db/harness_db/seed.py` in sync with any source/agent changes.

## Phase ordering

Phase A (code) before Phase B (agent prompts) — several prompt edits depend on
new commands existing. Phase C is independent and can land last. Within a phase,
items are independent unless noted.

---

## Phase A — move behavior into code

### A1. Enforce the prefilter in `api_search append` (analysis item 2)

**Problem:** The MCP searchers (linkedin, indeed, ziprecruiter, research) are
instructed to apply the disqualifier prefilter "by hand" — an LLM eyeballing
word-bounded-regex semantics that `job-preparer.md` itself forbids re-implementing
because "a hand-rolled `in` check would be wrong." `append_postings()`
(`api-search/api_search/core.py`) currently only dedups by URL.

**Change:**
- In `append_postings()` (or in `_append` in `api-search/api_search/__main__.py` —
  prefer `core.py` so the behavior is unit-testable), run each **incoming** posting
  through `prefilter_disqualifies(title, combined, load_prefilter())` from
  `harness_db.disqualifiers` before the merge. `combined` = title + location_note +
  description_summary + job_description_text (same spirit as `run()`).
- Postings already in the canonical file are not re-filtered (they passed when appended).
- Extend the return dict with a `disqualified` count; extend the printed line:
  `[API-SEARCH:APPEND:{PLATFORM}] +{N} new ({skipped} dup/blank, {disqualified} disqualified) — {total} total in {path}`.
- Tests (`api-search/tests/test_core.py`, `test_main.py`): batch containing a
  prefilter-matching posting is dropped and counted; non-matching postings pass;
  prefilter loading uses the DB-backed loader (mock/fixture as the existing
  disqualifier tests do).

**Acceptance:** an MCP searcher can write a completely unfiltered batch and the
canonical `{platform}-{date}.json` still contains zero prefilter-disqualified
postings. Do not change `run()` (the API pipeline already filters).

### A2. `harness-db companies seen` — replace per-company SQL loops (item 9)

**Problem:** Every searcher hand-writes one `mcp__sqlite__write_query`
INSERT…ON CONFLICT per unique company (dozens of tool calls per run, quote
escaping by instruction, per-agent flag policies encoded in prose SQL).

**Change:**
- New library module `harness-db/harness_db/companies.py` with an upsert function,
  and a new Typer sub-app: `harness-db companies seen --platform <platform> FILE...`
  (accept one or more jobs files in consolidator schema — the greenhouse agent has
  five, remotive three).
- Per-platform **flag policy table** in the module (one dict, single source of truth),
  reproducing the current agent SQL semantics:

  | platform(s) | remote_confirmed | canada_confirmed | notes | last_seen_date |
  |---|---|---|---|---|
  | linkedin, ziprecruiter | — | — | — | advance (MAX) |
  | indeed, adzuna | — | ratchet to 1 | — | advance |
  | greenhouse, lever, ashby, workable, recruitee | ratchet to 1 | ratchet to 1 | `Hiring on {ATS} (see posting URLs)` if empty | advance |
  | remotive, himalayas, wwr | ratchet to 1 | — | `Hiring on {board} (see posting URLs)` if empty | advance |
  | research | ratchet to 1 | ratchet to 1 | overwrite when provided (see below) | advance; also set `researched_date` |

  Ratchets use the MAX/COALESCE semantics already in the agent SQL (monotonic 0→1).
- **Research notes:** the research agent composes per-company judgment notes. Let
  posting objects carry an optional `company_notes` field in the batch JSON; the
  CLI uses it when present (research policy: overwrite when non-empty; all other
  platforms: only fill empty). Update the research agent's posting schema accordingly.
- Add a test asserting the policy table covers every platform in
  `consolidate_module.consolidator.PLATFORMS` (sync guard, same idea as the
  BUILTIN_SOURCES sync memory).
- Tests: `harness-db/tests/test_companies.py` — new company insert, ratchet
  up, never down, notes fill-if-empty vs research overwrite, multi-file input,
  quoting (company names with apostrophes), unknown platform → clear error.

**Agent updates (do in Phase B but driven by this):** every searcher replaces its
"Write Company Records to DB" section with one bash call, e.g.
`harness-db companies seen --platform greenhouse "$JOB_DATA_ROOT"/jobs/{greenhouse,lever,ashby,workable,recruitee}-{date}.json`
(each file's platform is in the file; if simpler, accept `--platform` per file or
read the platform from each file's `platform` key — implementer's choice, but the
agent-facing invocation must be a single command per agent). Then remove
`mcp__sqlite__write_query` (and `ToolSearch` where it was only used to load it)
from every searcher's frontmatter `tools` list.

### A3. Scorer response hardening (item 7)

**Problem:** In `scoring-module/scoring_module/scorer.py::_score_one`, a JSON
parse failure silently becomes a 50-score row, and `disqualifier_modifier` is
trusted unclamped (a hallucinated `+40` flows into `final_score`).

**Change:**
- On parse failure, **retry the API call once** (fresh sample, reuse `_retry`
  machinery or a simple second attempt). Only after the second failure apply the
  default-50 fallback, and prefix `scoring_notes` with `[PARSE-FAILED]` so the
  rows are findable/regradable (`harness-db postings` filtering should surface it).
- Clamp `disqualifier_modifier`: must be an `int` (else 0) and within
  `[sum_of_enabled_negative_modifiers, 0]` computed from
  `load_disqualifiers()["scoring_modifiers"]`. (All built-in modifiers are ≤ 0; a
  positive or out-of-range value from the model is clamped, and a `[WARN]` is
  printed to stderr.)
- Validate `dimension_scores` values to the 1–10 range before
  `_compute_base_score` (out-of-range → treat that dim as missing so the existing
  fallback path applies).
- Tests in `scoring-module/tests/test_scorer.py`: parse-fail→retry→success path,
  double-fail → `[PARSE-FAILED]` note, modifier clamping (positive value, huge
  negative value, non-int), out-of-range dimension scores.

### A4. Deterministic candidate summary (item 6)

**Problem:** job-seeker Step 0 has a sonnet model re-invent
`candidate-summary.json` (headline, notable, years_experience, stack…) from the
resume YAML **every day**. Every searcher's queries and the scorer's cached system
prompt derive from this file — it is the single highest-leverage hallucination
point in the pipeline.

**Change:**
1. **New per-user config keys** (via `harness_db.config_store`, edited in the
   existing Settings → Config panels of both TUI and web — these are generic
   key-value config items, so register them in the config catalog/seed the same
   way `RESUME_FILE` etc. were in spec 12):
   - `CANDIDATE_HEADLINE` (e.g. "Principal/Consulting Engineer — Cloud, Healthcare, AI/ML")
   - `CANDIDATE_NOTABLE` (e.g. "13 years at Oracle (OCI, Public Cloud, Health & AI)")
   - `CANDIDATE_YEARS_EXPERIENCE` (int)
   - `CANDIDATE_WORK_TYPE` (default "fully remote")
   - `CANDIDATE_ELIGIBILITY` (default "Canada-eligible")
   - `CANDIDATE_EMPLOYMENT` (csv, default "full-time,contract,freelance")
   - `CANDIDATE_COMP_FLOOR_CAD` (optional int)
2. **One-time import:** during `ensure_schema_and_seed` (same pattern as the other
   spec-12 migrations), if these keys are unset for the user and an existing
   `$JOB_DATA_ROOT/candidate-summary.json` is present, import its values
   (`headline`, `notable`, `years_experience`, `requirements.*`) into the user's
   config. Existing installs migrate with zero typing.
3. **New command `harness-db candidate-summary [--write] [--force]`:** assembles
   the summary deterministically —
   - `name`, `location` from the resume YAML (`cv.name`, `cv.location`; resume path
     via the existing config resolution).
   - `stack` from the resume's skills section: split each `cv.sections.skills[].details`
     on commas, strip, preserve order, dedupe.
   - `target_titles`, `seniority_keywords`, `domains` from `harness_db.target_roles`
     (the DB, same data `target-roles show` renders).
   - `headline`, `notable`, `years_experience`, `requirements` from the config keys above.
   - `generated` = today, plus an `inputs_hash` (hash of resume file bytes +
     rendered target roles + the config values). `--write` writes
     `$JOB_DATA_ROOT/candidate-summary.json` **only when the hash differs** from
     the existing file's (or `--force`); always prints the JSON and whether it
     wrote. Keep the output schema **byte-compatible** with the current file —
     `api_search.candidate`, `harness_db.profile`, and the scorer all read it.
4. **job-seeker.md Step 0** shrinks to: activate venv, run
   `harness-db candidate-summary --write`, done. Delete the whole synthesis
   instruction block and the JSON template (≈40 lines of prompt).
5. Tests: new `harness-db/tests/test_candidate_summary.py` — assembly from a
   fixture resume YAML + seeded target roles + config keys; hash-based idempotence;
   import-once migration; missing config keys produce empty strings, not crashes.

### A5. Fix `agent_io.build_prepare_prompt` (item 4)

**Problem:** `harness-db/harness_db/agent_io.py::build_prepare_prompt` tells
job-preparer to "go straight to running the full pipeline (resume-tailor,
rendercv, cover-letter-creator, rendercv)". This contradicts the phase protocol:
job-preparer defaults to `phase: score` when no phase is given, the prompt asks it
to *skip* scoring, and it implies cover letters, which are opt-in. The TUI/web
"Prepare" button behavior currently depends on model improvisation.

**Change:** rewrite the prompt to the phase protocol:

```
Use the job-preparer agent with phase: prepare.
selected_urls: ["<posting.url>"]
The posting is already 'selected' in the DB. Prepare the tailored resume and
final report only — do NOT generate a cover letter (cover letters are opt-in
and handled separately).
```

Update `harness-db/tests/test_agent_io.py`. Verify the web runner and TUI pass
this prompt through unchanged (no other call sites encode the old wording —
grep `tui/` and `web/`).

---

## Phase B — agent prompt & docs sync

### B1. Purge `disqualifiers.yaml` references from searcher agents (item 1) — depends on A1

Seven files still call `$JOB_DATA_ROOT/disqualifiers.yaml` "the single
user-editable source of truth": `job-seeker-linkedin.md`, `-indeed.md`,
`-ziprecruiter.md`, `-research.md`, `-adzuna.md`, `-greenhouse.md`,
`-remotive.md`. The DB has been canonical since spec 12; the file is a legacy
fallback only.

**Change:** in each file, replace the entire "Hard exclusions — early
disqualification" block with 2–3 lines:

- API-module agents (adzuna, greenhouse, remotive): "Hard disqualifiers are
  data-driven, per-user, stored in the harness DB, and applied by the
  `api_search` module — you do not read or apply them."
- MCP/batch agents (linkedin, indeed, ziprecruiter, research): "Hard
  disqualifiers are data-driven, per-user, stored in the harness DB, and enforced
  by `api_search append` when you merge your batch — you do not read or apply
  them. Do not invent exclusions; when eligibility is ambiguous, keep the posting
  for the scorer." Their remote/seniority/eligibility judgment instructions stay.

Also update the matching prose in `job-seeker.md` Step 0d and `CLAUDE.md`'s
Disqualifiers section if it still implies searchers read the rules themselves.

### B2. Delete the prose schema from job-seeker.md (item 3)

**Change:** delete Step 0b entirely (the three `mcp__sqlite__create_table`
blocks). The schema is owned by `harness_db.models` and created/seeded by
`ensure_schema_and_seed`, which `harness-db sources enabled` (Step 0c) already
runs. Renumber/reorder the remaining Step 0 sub-steps. Remove
`mcp__sqlite__create_table` from job-seeker's frontmatter tools; audit the
remaining `mcp__sqlite__*` tools and drop any no longer used by the instructions
(after B1/A2 the orchestrator likely needs none).

### B3. Remove searcher-count drift (item 5)

CLAUDE.md says "spawns six platform searchers", `job-seeker.md` says "eight",
reality is seven sources. **Change:** remove the numerals everywhere (CLAUDE.md
agent list + workflow section, `job-seeker.md` intro, agent `description` fields
if any carry counts) and phrase as "the enabled sources from the DB sources
catalog". Counts in prompts are what models pattern-match when deciding
something is "missing".

### B4. Model downgrades for deterministic searchers (item 8)

`job-seeker-adzuna.md`, `job-seeker-greenhouse.md`, `job-seeker-remotive.md`
change `model: sonnet` → `model: haiku`. Their entire job after A2 is "run N CLI
commands, forward output lines". Keep `job-seeker-research` and both
orchestrators on sonnet. CV agents stay opus.

### B5. CV agent tool trims + JD supply guarantee (item 11) — decision applied

- **Trim frontmatter `tools`** of `resume-tailor.md`, `cover-letter-creator.md`,
  `resume-evaluator.md` to what their instructions actually use:
  `Read, Edit, Write, Bash, ToolSearch` (drop `NotebookEdit, CronCreate, CronDelete,
  CronList, EnterWorktree, ExitWorktree, Monitor, PushNotification, RemoteTrigger,
  ScheduleWakeup, Skill, TaskCreate, TaskGet, TaskList, TaskUpdate`).
- **Add `WebFetch` to resume-tailor only** (interactive mode fetches the posting;
  its step 2 says "read the job posting" from a link).
- **job-preparer always supplies the JD:** in `job-preparer.md` Step 7b, when a
  selected posting's `job_description_text` is empty in the DB, job-preparer
  fetches the URL itself (it has WebFetch) and passes the text inline; the
  `# omit this line if unavailable` escape hatch changes to "if the fetch also
  fails, say so explicitly in the spawn prompt and in the final report". Delete
  the "(resume-tailor will fetch the URL itself)" claim.

### B6. Slim the two orchestrator prompts (item 10) — after B1/B2/A4 land

`job-seeker.md` (~19 KB) and `job-preparer.md` (~21.6 KB) cost ≈5K tokens per
spawn; job-preparer is spawned up to **three times** per run. Move
rationale/history to docs, keep imperative instructions.

- Create `docs/design-notes.md` holding the *why* paragraphs: why scoring is a
  module not an agent, why there is no worker/team layer (job-preparer Step 7
  preamble), why the prefilter is word-bounded, why the probe step is mandatory
  and the hard stop deliberate, the inline-fallback rationale, the
  "data-driven and per-user" config history.
- In the agent files keep: step sequence, exact commands, exact output/report
  formats, schemas of files they themselves write. Cut: repeated explanations
  (the "data-driven and per-user" paragraph appears 3× in job-seeker.md alone),
  historical comparisons, restated CLAUDE.md content.
- **Target: ≥40% size reduction in both files with zero behavioral instructions
  lost.** Diff-review against the checklist of steps before/after.
- Leave the Post-Task Reflection / extraction-candidate blocks functionally
  intact in all agents (they are load-bearing for the error-transparency
  contract), but they may be tightened verbatim-identically across all 13 files.

### B7. Document the deliberate hard stop (item 12) — decision: keep behavior

In `job-seeker.md` Step 1, add one line: "This hard stop is deliberate (spec 14):
a partial run silently missing a major source is worse than a failed run —
do not soften it to degrade-and-continue." No behavior change. Ensure the failed
probe name reaches the search report's Execution Issues section (already
specified — verify wording survives B6).

### B8. CLAUDE.md + docs/ sweep — last in phase

After B1–B7: update `CLAUDE.md` (disqualifiers paragraph, candidate-summary
generation, `companies seen` mention, searcher counts) and **all** of `docs/*`:
`harness-workflow.mmd` and `data-flow.mmd` (Step 0b removal, companies CLI,
candidate-summary command), `database.md` (new config keys), `onboarding.md`
(Settings now includes candidate fields), `candidate-sources.md`,
`job-states.md`, `embeddings.md` (review even if unchanged). Validate diagrams:
`nox -s docs_mermaid`.

---

## Phase C — operational hardening (item 13)

### C1. Adzuna rate limiting + 429 backoff in `api_search`

Adzuna's free tier 429s under the current parallel/burst fetch (observed: 4 of 8
queries failed in one run). In the adzuna source (`api-search/api_search/sources.py`):
- Serialize its queries with a configurable inter-request delay (default ~1.5 s,
  config key in the source's `sources_default.yaml`/`load_config()` entry).
- On HTTP 429: honor `Retry-After` if present, else exponential backoff (2 s, 4 s,
  8 s), max 3 retries per query; after that, log a `[WARN]` with the failed query
  and continue (partial results are acceptable and reported).
- Tests with a mocked client: 429-then-200 succeeds; 429×4 drops the query but
  not the run; delay/backoff values respected (patch `time.sleep`).

### C2. ATS slug validation command

Board slugs in `sources_default.yaml` go stale fast. Add
`python -m api_search probe-slugs [<source> ...]` (default: all slug-based
sources — greenhouse, lever, ashby, workable, recruitee):
- For each configured slug, hit the source's cheap probe endpoint (the boards
  JSON API root, e.g. `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=false`,
  `api.lever.co/v0/postings/{slug}?limit=1`, `api.ashbyhq.com/posting-api/job-board/{slug}`,
  etc.) with a short timeout.
- Report per slug: `OK (N jobs)` / `EMPTY` / `GONE (404)` / `ERROR (status)`.
  Summary line with counts; exit code 1 if any `GONE`.
- The command only **reports** — relocation/removal of slugs stays a human (or
  agent-assisted) decision: prefer relocating a company to its new ATS over
  deleting it.
- Tests with mocked client covering each status bucket.

---

## Suggested implementation order & commits

1. A1 prefilter-in-append (`api-search`)
2. A2 `companies seen` (`harness-db`) + sync-guard test
3. A3 scorer hardening (`scoring-module`)
4. A4 candidate-summary command + config keys + import (`harness-db`, TUI/web Settings exposure)
5. A5 `build_prepare_prompt` (`harness-db`)
6. B1+B2+B3 searcher/orchestrator prompt sync (one commit per agent file group is fine)
7. B4 model downgrades
8. B5 CV agent tools + JD guarantee
9. B6 orchestrator slimming + `docs/design-notes.md`
10. B7 hard-stop note
11. B8 CLAUDE.md + docs sweep + `nox -s docs_mermaid`
12. C1 Adzuna throttle
13. C2 probe-slugs

Each numbered step: own commit, module `nox -t fix` + `nox -s tests` green before
moving on.

## Acceptance checklist (whole spec)

- [ ] No agent `.md` file references `disqualifiers.yaml`, contains a `CREATE TABLE`
      column list, applies prefilter matching itself, or hand-writes companies SQL.
- [ ] `grep -rn "six platform\|eight platform" CLAUDE.md .claude/agents/` → empty.
- [ ] A run with an unfiltered MCP batch produces a prefilter-clean canonical file (A1 test).
- [ ] Companies flag policy covers every platform in `consolidator.PLATFORMS` (A2 test).
- [ ] Scorer never persists an out-of-range modifier or unmarked parse-failure row (A3 tests).
- [ ] `harness-db candidate-summary --write` is idempotent (hash) and byte-compatible
      with current consumers (`api_search.candidate`, `harness_db.profile`, scorer) (A4 tests).
- [ ] TUI/web "Prepare" button sends the `phase: prepare` protocol prompt (A5 test).
- [ ] `job-seeker.md` and `job-preparer.md` each ≥40% smaller; step checklists unchanged.
- [ ] All module test suites green; `nox -s docs_mermaid` green.
- [ ] CLAUDE.md and every `docs/*` file reviewed/updated.
