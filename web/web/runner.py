"""Stream a harness agent run as human-readable display lines.

Dual-mode, selected by the RUNNER_URL env var:
  * unset  -> run the `claude` CLI locally as a subprocess (dev / host).
  * set    -> consume an SSE stream from the agent-runner service (Docker).

Both paths share format_event so output looks identical regardless of source.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator

import httpx
from harness_db.agent_io import format_event

_RUNNER_URL_ENV = "RUNNER_URL"
_RUNNER_RUN_PATH = "/run"
# Generous ceiling: an agent run (scoring/preparing) can take minutes.
_REMOTE_TIMEOUT_SECONDS = 1800.0

_CLAUDE_CMD = ("claude", "--print", "--output-format", "stream-json", "--verbose")
_SUBPROCESS_ENV = {"TERM": "dumb", "NO_COLOR": "1"}
_SSE_DATA_PREFIX = "data:"


def _format_raw_line(raw: str) -> list[str]:
    """Parse one stream-json line into display lines; pass through non-JSON."""
    line = raw.strip()
    if not line:
        return []
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return [line]
    return format_event(event)


async def stream_agent(prompt: str) -> AsyncIterator[str]:
    runner_url = os.environ.get(_RUNNER_URL_ENV)
    if runner_url:
        async for text in _stream_remote(runner_url, prompt):
            yield text
    else:
        async for text in _stream_local(prompt):
            yield text


async def _stream_local(prompt: str) -> AsyncIterator[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *_CLAUDE_CMD,
            prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, **_SUBPROCESS_ENV},
        )
    except FileNotFoundError:
        yield "Error: `claude` CLI not found on PATH."
        return
    except Exception as exc:  # pragma: no cover - defensive
        yield f"Error launching claude: {exc}"
        return

    assert proc.stdout is not None
    async for raw in proc.stdout:
        for text in _format_raw_line(raw.decode("utf-8", errors="replace")):
            yield text
    await proc.wait()
    if proc.returncode != 0:
        yield f"✗ claude exited with code {proc.returncode}"


async def _stream_remote(runner_url: str, prompt: str) -> AsyncIterator[str]:
    url = runner_url.rstrip("/") + _RUNNER_RUN_PATH
    try:
        async with httpx.AsyncClient(timeout=_REMOTE_TIMEOUT_SECONDS) as client:
            async with client.stream("POST", url, json={"prompt": prompt}) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_lines():
                    if not raw.startswith(_SSE_DATA_PREFIX):
                        continue
                    payload = raw[len(_SSE_DATA_PREFIX) :].strip()
                    for text in _format_raw_line(payload):
                        yield text
    except httpx.HTTPError as exc:
        yield f"Error contacting agent-runner at {url}: {exc}"
