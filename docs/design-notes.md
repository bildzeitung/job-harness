# Design Notes — the *why* behind the pipeline

The agent prompts (`.claude/agents/*.md`) hold imperative instructions only:
step sequences, exact commands, exact output/report formats. The rationale that
used to bloat those prompts lives here, so the prompts stay short (they are paid
on every spawn — `job-preparer` is spawned up to three times per run) and the
reasoning is reviewed in one place. When a prompt says "see design-notes", this
is the file.

## Configuration is data-driven and per-user

Every user-facing input — sources, disqualifiers, target roles, the candidate
config keys, and the file pointers (`RESUME_FILE`, `JOB_DATA_ROOT`, Adzuna
creds) — is stored per-user in the harness DB and edited from the TUI/web
**Settings** tab (or the `harness-db` CLI). The pattern is "catalog + per-user
selection": a catalog table holds the available items (built-ins have
`owner_uid` NULL), and a `user_*` join table records which a user enabled.

On first run the harness seeds a `default` user and imports any legacy on-disk
config — `sources-config.json`, `disqualifiers.yaml`, `target-roles.md`,
`candidate-summary.json`, and the env config values — so existing single-user
installs migrate with zero typing. Those files are now **legacy fallbacks only**;
the DB is the source of truth. This is why no agent reads `disqualifiers.yaml`
or hand-writes a schema any more — the loaders (`harness_db.disqualifiers`,
`…sources_store`, `…target_roles`, `…config_store`) own it.

## Scoring is a module, not an agent

`scoring_module` calls the Claude API directly (with a cached system prompt)
rather than being a spawned agent. It is deterministic plumbing around one LLM
call per posting: it computes `base_score` from the dimension weights itself
(the model emits the un-multiplied average ~40% of the time), retries a parse
failure once, clamps the disqualifier modifier to the enabled-modifier range,
and ratchets the company flags. None of that benefits from an agent's tool loop,
and an agent would re-derive the arithmetic unreliably. `job-preparer` runs it on
a batch; the TUI/web "Score" button runs it on one URL.

## The prefilter is word-bounded — never re-implement it by hand

The hard prefilter (`harness_db.disqualifiers.prefilter_disqualifies`) matches
case-insensitively but **word-bounded**: a token like `defi` matches the whole
word (and `DeFi`) but not `defines`/`defining`, and a phrase glued onto
`/canada` (e.g. `remote - us/canada`) does not fire so Canada-eligible postings
survive. A hand-rolled `in` substring check would mis-fire on both counts, which
is why every consumer goes through the one shared matcher: `api_search`
(`run()` and `append`) for the searchers, and `harness-db prefilter` for
`job-preparer`. Agents must not eyeball it.

## The MCP probe step is mandatory and the hard stop is deliberate

Session-dependent MCP servers (LinkedIn, Indeed, ZipRecruiter) can be
schema-registered in ToolSearch yet disconnected, and LinkedIn can be partially
functional (profile endpoints answer while job-search endpoints do not). Probing
a proxy endpoint masks that and yields silent 0-result runs, so `job-seeker`
Step 1 probes the **actual** tools the searchers will call.

If an *enabled* source's probe fails, the run **stops**. This hard stop is
deliberate (spec 14): a partial run that silently drops a major source is worse
than a failed run the user can re-trigger. Do not soften it to
degrade-and-continue.

## The inline fallback when the Agent tool is unavailable

`job-seeker` may itself be spawned as a sub-agent (e.g. by the `job-search`
skill), in which case the `Agent` tool is unavailable and spawning searchers
fails with *"Agent tool unavailable in sub-agent session"*. That must **not** be
reported as `0` results: `job-seeker` recovers every enabled source inline — the
deterministic sources by running the `api_search` modules itself, the MCP
sources by calling their tools directly, and research by reasoning over its own
WebSearch/WebFetch results — exactly as each sub-agent would.

## No worker/team layer under job-preparer

`job-preparer` spawns `resume-tailor` (and optionally `cover-letter-creator`)
directly, one per selected job, in parallel — there is no intermediate
worker/team/coordinator layer. The phase protocol (`score` → `prepare` →
optional `cover-letters`) is the only structure; adding a team layer would buy
nothing but more prompt surface and more places for the plan to drift. The
calling skill owns all user interaction because a sub-agent's questions do not
surface to the user.
