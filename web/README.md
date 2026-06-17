# job-web — Matchwright Reflex web interface

A reactive web UI for Matchwright, at parity with the Textual TUI: browse
jobs and companies, sort, view details, change statuses, score a single posting
(via the `scoring_module`), and trigger the `job-preparer` agent — all with
live-streamed output.

It reuses the shared data layer in `harness-db` (`queries`, `config`,
`agent_io`), so it always reflects the same SQLite DB as the TUI and pipeline.

## Local development

```bash
uv pip install -e ./harness-db[dev] -e ./web[dev]
cd web
JOB_DATA_ROOT=/path/to/job-data reflex run
# open http://localhost:3000
```

With no `RUNNER_URL` set, "Score new" / "Prepare" run the `claude` CLI directly
on your machine (it must be on `PATH` and logged in).

## Docker

Two images, orchestrated by `web/docker-compose.yml`:

- **web** — lean Reflex app. No `claude` CLI, no credentials. Handles browsing
  and status updates on its own.
- **agent-runner** — the only container with the `claude` CLI + mounted
  credentials; exposes an SSE endpoint the web app calls when `RUNNER_URL` is set.

```bash
export JOB_DATA_ROOT=/abs/path/to/job-data

# Browsing + status updates only:
docker compose -f web/docker-compose.yml up --build web

# Add in-browser agent triggering:
docker compose -f web/docker-compose.yml up --build
```

The DB is located by `HARNESS_DB` (a path straight to the SQLite file), falling
back to the bind-mounted `$JOB_DATA_ROOT/jobs/postings.db` (`/data/jobs/postings.db`)
when unset. The web **Settings** tab edits the per-user config, sources,
disqualifiers, and target roles in that same DB.

### Notes / caveats

- Agent triggering in Docker is the heaviest, last-verified path: the
  `agent-runner` mounts the repo (for `CLAUDE.md`, `.claude/agents`, modules) and
  your `~/.claude/.credentials.json`, and installs the full harness (incl.
  rendercv). Some agents may also need MCP servers configured.
- WAL is enabled best-effort in `harness_db.make_engine`; on a read-only DB it is
  skipped so reads still work.
