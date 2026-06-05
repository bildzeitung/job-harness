"""Tests for harness_db.agent_io event formatting and prompt builders."""

from __future__ import annotations

from dataclasses import dataclass

from harness_db.agent_io import (
    REJECTABLE_STATES,
    build_prepare_prompt,
    build_score_command,
    format_event,
)


def test_format_event_system_init():
    assert format_event({"type": "system", "subtype": "init"}) == ["── session started ──"]


def test_format_event_assistant_text_splits_lines():
    event = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "line one\nline two"}]},
    }
    assert format_event(event) == ["line one", "line two"]


def test_format_event_assistant_tool_use_task_and_bash():
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Task", "input": {"subagent_type": "job-preparer"}},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                {"type": "tool_use", "name": "Read", "input": {"file_path": "/tmp/x"}},
            ]
        },
    }
    assert format_event(event) == [
        "→ Task: job-preparer",
        "→ Bash: ls -la",
        "→ Read: /tmp/x",
    ]


def test_format_event_tool_detail_is_truncated():
    long_cmd = "x" * 250
    event = {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "Bash", "input": {"command": long_cmd}}]
        },
    }
    (line,) = format_event(event)
    # "→ Bash: " prefix + 100 truncated chars.
    assert line == "→ Bash: " + "x" * 100


def test_format_event_result_ok_and_error():
    assert format_event({"type": "result", "duration_ms": 12}) == ["✓ done (12 ms)"]
    assert format_event({"type": "result", "is_error": True}) == ["✗ error"]


def test_format_event_unknown_returns_empty():
    assert format_event({"type": "user"}) == []


@dataclass
class _FakePosting:
    url: str
    company: str | None
    title: str | None


def test_build_score_command_targets_scoring_module():
    p = _FakePosting(url="https://x/1", company="Acme", title="Engineer")
    cmd = build_score_command(p)
    # Interpreter-agnostic: no leading python — each runner prepends sys.executable.
    assert cmd == ["-m", "scoring_module", "--url", "https://x/1"]


def test_build_prepare_prompt_includes_url():
    p = _FakePosting(url="https://x/3", company="Acme", title="Eng")
    prompt = build_prepare_prompt(p)
    assert "https://x/3" in prompt
    assert "job-preparer" in prompt


def test_rejectable_states_membership():
    assert "selected" in REJECTABLE_STATES
    assert "applied" not in REJECTABLE_STATES
