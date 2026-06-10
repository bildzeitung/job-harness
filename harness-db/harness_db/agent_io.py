"""Shared helpers for launching harness work from the TUI and web app.

Holds the stream-json event formatter (for agent runs), the single-posting
scoring command builder, and the prepare-agent prompt builder, so both
front-ends render output and invoke work identically.
"""

from __future__ import annotations

from typing import Protocol

__all__ = [
    "REJECTABLE_STATES",
    "PostingLike",
    "format_event",
    "build_score_command",
    "build_prepare_prompt",
]

# Statuses a posting may be in for a "reject" action to be allowed.
REJECTABLE_STATES: frozenset[str] = frozenset({"selected", "scored", "new", "prepared"})

# Max characters of a tool_use detail line to show before truncating.
_TOOL_DETAIL_MAXLEN = 100


class PostingLike(Protocol):
    """Minimal posting shape needed to build agent prompts.

    Satisfied by both the SQLAlchemy ``Posting`` model and the web ``PostingVM``.
    """

    url: str
    company: str | None
    title: str | None


def format_event(event: dict) -> list[str]:
    """Turn one stream-json event into human-readable display lines."""
    etype = event.get("type")

    if etype == "system" and event.get("subtype") == "init":
        return ["── session started ──"]

    if etype == "assistant":
        out: list[str] = []
        for block in event.get("message", {}).get("content", []):
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    out.extend(text.splitlines())
            elif btype == "tool_use":
                name = block.get("name", "?")
                inp = block.get("input", {})
                if name == "Task":
                    detail = inp.get("subagent_type") or inp.get("description") or ""
                elif name == "Bash":
                    detail = inp.get("command", "")
                else:
                    detail = inp.get("description") or inp.get("file_path") or ""
                detail = str(detail).replace("\n", " ")[:_TOOL_DETAIL_MAXLEN]
                out.append(f"→ {name}: {detail}" if detail else f"→ {name}")
        return out

    if etype == "result":
        dur = event.get("duration_ms")
        suffix = f" ({dur} ms)" if dur is not None else ""
        if event.get("is_error"):
            return [f"✗ error{suffix}"]
        return [f"✓ done{suffix}"]

    return []


def build_score_command(posting: PostingLike) -> list[str]:
    """Interpreter-agnostic argv to score a single posting via the scoring_module.

    Returned without a leading interpreter so each runner can prepend its own
    ``sys.executable`` (host venv for the TUI/local web, the agent-runner's venv
    in Docker). The module reads the posting from the DB, scores it, persists the
    result, and ratchets the company flags — no agent spawning involved.
    """
    return ["-m", "scoring_module", "--url", posting.url]


def build_prepare_prompt(posting: PostingLike) -> str:
    """Prompt to prepare a single 'selected' posting via the job-preparer phase protocol.

    Uses ``phase: prepare`` explicitly (job-preparer defaults to ``phase: score``)
    and excludes cover letters, which are opt-in and handled separately.
    """
    return (
        "Use the job-preparer agent with phase: prepare.\n"
        f'selected_urls: ["{posting.url}"]\n'
        "The posting is already 'selected' in the DB. Prepare the tailored resume and "
        "final report only — do NOT generate a cover letter (cover letters are opt-in "
        "and handled separately)."
    )
