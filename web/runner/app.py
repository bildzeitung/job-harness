"""Standalone SSE service that runs the `claude` CLI and streams its output.

Used by the web app's runner.py in 'remote' mode (Docker): it isolates the
`claude` CLI and OAuth credentials in a dedicated container. It runs the agent in
the harness repo directory (REPO_DIR) so subagents find CLAUDE.md, .claude/agents,
and the Python modules, then forwards each raw stream-json line as one SSE event.
"""

from __future__ import annotations

import asyncio
import os
import sys

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

_CLAUDE_CMD = ("claude", "--print", "--output-format", "stream-json", "--verbose")
_SUBPROCESS_ENV = {"TERM": "dumb", "NO_COLOR": "1"}
# Directory the harness repo is mounted at; claude runs here for agent context.
_REPO_DIR = os.environ.get("REPO_DIR", "/repo")
_RUNNER_PORT = int(os.environ.get("RUNNER_PORT", "8100"))

app = FastAPI(title="job-harness agent-runner")


class RunRequest(BaseModel):
    prompt: str


class CommandRequest(BaseModel):
    # Interpreter-agnostic argv (e.g. ["-m", "scoring_module", "--url", ...]);
    # this service prepends its own python so the work runs in the harness venv.
    argv: list[str]


async def _stream_subprocess(*cmd: str):
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=_REPO_DIR,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env={**os.environ, **_SUBPROCESS_ENV},
    )
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode("utf-8", errors="replace").rstrip("\n")
        if line:
            yield f"data: {line}\n\n"
    await proc.wait()


def _events(prompt: str):
    return _stream_subprocess(*_CLAUDE_CMD, prompt)


def _command_events(argv: list[str]):
    return _stream_subprocess(sys.executable, *argv)


@app.post("/run")
async def run(req: RunRequest) -> StreamingResponse:
    return StreamingResponse(_events(req.prompt), media_type="text/event-stream")


@app.post("/run-command")
async def run_command(req: CommandRequest) -> StreamingResponse:
    return StreamingResponse(_command_events(req.argv), media_type="text/event-stream")


@app.get("/health")
def health() -> dict:
    return {"ok": True}
