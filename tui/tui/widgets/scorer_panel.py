from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime

from harness_db.agent_io import format_event
from textual import work
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import RichLog
from textual.worker import get_current_worker

_DEBUG_LOG = os.environ.get("SCORER_DEBUG_LOG")


def _dbg(msg: str) -> None:
    if not _DEBUG_LOG:
        return
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with open(_DEBUG_LOG, "a") as f:
        f.write(f"{ts}  {msg}\n")


class ScorerPanel(Widget):
    """Runs `claude --print` with stream-json output and renders events into a RichLog."""

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=False, wrap=True, markup=False)

    def run_prompt(self, prompt: str) -> None:
        log = self.query_one(RichLog)
        log.clear()
        log.write("Launching…")
        _dbg(f"run_prompt called, prompt[:80]={prompt[:80]!r}")
        self._stream_claude(prompt)

    def run_command(self, argv: list[str]) -> None:
        """Run a deterministic harness command (e.g. single-posting scoring).

        Unlike run_prompt, this streams the command's plain stdout verbatim — no
        agent, no stream-json. The argv omits the interpreter; we prepend the
        running TUI's own python so it executes in the harness venv.
        """
        log = self.query_one(RichLog)
        log.clear()
        log.write("Launching…")
        _dbg(f"run_command called, argv={argv!r}")
        self._stream_command(argv)

    @work(thread=True, exclusive=True)
    def _stream_command(self, argv: list[str]) -> None:
        log = self.query_one(RichLog)
        _dbg("worker started (command)")

        try:
            proc = subprocess.Popen(
                [sys.executable, *argv],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )
            _dbg(f"Popen ok, pid={proc.pid}")
        except Exception as exc:
            _dbg(f"Popen failed: {exc}")
            self.app.call_from_thread(log.write, f"Error launching command: {exc}")
            self.app.call_from_thread(self.app.notify, f"Launch failed: {exc}", severity="error")
            return

        worker = get_current_worker()
        try:
            for raw_line in iter(proc.stdout.readline, b""):
                if worker.is_cancelled:
                    _dbg("worker cancelled, breaking")
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if line:
                    self.app.call_from_thread(log.write, line)
        except Exception as exc:
            _dbg(f"read error: {exc}")
        finally:
            if proc.poll() is None:
                proc.terminate()

        if proc.returncode == 0:
            self.app.call_from_thread(self.app.notify, "Done!", severity="information")
        else:
            self.app.call_from_thread(
                self.app.notify, f"Failed (exit {proc.returncode})", severity="error"
            )
        _dbg(f"command worker finished, returncode={proc.returncode}")

    @work(thread=True, exclusive=True)
    def _stream_claude(self, prompt: str) -> None:
        log = self.query_one(RichLog)
        _dbg("worker started (stream-json)")

        try:
            proc = subprocess.Popen(
                [
                    "claude",
                    "--print",
                    "--output-format",
                    "stream-json",
                    "--verbose",
                    prompt,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )
            _dbg(f"Popen ok, pid={proc.pid}")
        except Exception as exc:
            _dbg(f"Popen failed: {exc}")
            self.app.call_from_thread(log.write, f"Error launching claude: {exc}")
            self.app.call_from_thread(self.app.notify, f"Launch failed: {exc}", severity="error")
            return

        total_lines = 0
        worker = get_current_worker()
        try:
            for raw_line in iter(proc.stdout.readline, b""):
                if worker.is_cancelled:
                    _dbg("worker cancelled, breaking")
                    break
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    _dbg(f"non-json line: {line[:120]!r}")
                    self.app.call_from_thread(log.write, line)
                    continue
                display = format_event(event)
                _dbg(f"event type={event.get('type')} -> {len(display)} lines")
                for text in display:
                    total_lines += 1
                    self.app.call_from_thread(log.write, text)
        except Exception as exc:
            _dbg(f"read error: {exc}")
        finally:
            _dbg(f"loop done: total_lines={total_lines} returncode={proc.poll()}")
            if proc.poll() is None:
                proc.terminate()

        if proc.returncode == 0:
            self.app.call_from_thread(self.app.notify, "Done!", severity="information")
        else:
            self.app.call_from_thread(
                self.app.notify, f"Failed (exit {proc.returncode})", severity="error"
            )
        _dbg(f"worker finished, returncode={proc.returncode}")
