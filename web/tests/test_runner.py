"""Tests for the agent-stream line formatter."""

from __future__ import annotations

import json

from web.runner import _format_raw_line


def test_blank_line_yields_nothing():
    assert _format_raw_line("   ") == []


def test_non_json_line_passes_through():
    assert _format_raw_line("plain text") == ["plain text"]


def test_json_event_is_formatted():
    line = json.dumps({"type": "system", "subtype": "init"})
    assert _format_raw_line(line) == ["── session started ──"]


def test_json_result_event():
    line = json.dumps({"type": "result", "duration_ms": 5})
    assert _format_raw_line(line) == ["✓ done (5 ms)"]
