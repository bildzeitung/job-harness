from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Static
from textual.worker import work

STATE_STYLES: dict[str, str] = {
    "new": "bold green",
    "scored": "bold cyan",
    "selected": "bold yellow",
    "skipped": "dim red",
    "prepared": "bold magenta",
    "applied": "bold red",
}

_DATE_WIDTH = 12
_STATE_WIDTH = 10
_COL_PADDING = 6  # borders, scrollbar, gutters
_OUTPUT_PANEL_HEIGHT = 20
_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')


class JobViewerApp(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("p", "prepare_job", "Prepare"),
        Binding("a", "mark_applied", "Applied"),
        Binding("o", "toggle_output", "Output", show=False),
        Binding("j", "scroll_details_down", "Scroll ↓", show=False),
        Binding("k", "scroll_details_up", "Scroll ↑", show=False),
    ]

    def __init__(self, db_path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db_path = db_path
        self._postings: list = []
        self._details_visible = False
        self._job_col_key = None
        self._state_col_key = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield DataTable(id="jobs-table", cursor_type="row", zebra_stripes=True)
            with ScrollableContainer(id="details-panel"):
                yield Static(id="details-content")
            with ScrollableContainer(id="output-panel"):
                yield Static(id="output-content")
        yield Footer()

    def on_mount(self) -> None:
        from tui.db import get_postings, make_engine

        try:
            engine = make_engine(self.db_path)
            self._postings = get_postings(engine)
        except Exception as e:
            self.exit(f"Error reading database: {e}")
            return

        table = self.query_one("#jobs-table", DataTable)
        job_width = max(20, self.size.width - _DATE_WIDTH - _STATE_WIDTH - _COL_PADDING)
        self._job_col_key = table.add_column("Job", width=job_width)
        table.add_column("Date", width=_DATE_WIDTH)
        self._state_col_key = table.add_column("State", width=_STATE_WIDTH)

        for posting in self._postings:
            status = posting.status or "new"
            table.add_row(
                posting.display_name,
                posting.display_date,
                Text(status, style=STATE_STYLES.get(status, "white")),
                key=posting.url,
            )

        self.title = f"Job Viewer — {len(self._postings)} postings"
        self.query_one("#details-panel").display = False
        self.query_one("#output-panel").display = False

    def action_refresh(self) -> None:
        from tui.db import get_postings, make_engine

        try:
            engine = make_engine(self.db_path)
            self._postings = get_postings(engine)
        except Exception as e:
            self.notify(f"Refresh failed: {e}", severity="error")
            return

        table = self.query_one("#jobs-table", DataTable)
        table.clear()
        for posting in self._postings:
            status = posting.status or "new"
            table.add_row(
                posting.display_name,
                posting.display_date,
                Text(status, style=STATE_STYLES.get(status, "white")),
                key=posting.url,
            )

        self.title = f"Job Viewer — {len(self._postings)} postings"
        self.query_one("#details-panel").display = False
        self._details_visible = False

    def on_resize(self) -> None:
        if self._job_col_key is None:
            return
        table = self.query_one("#jobs-table", DataTable)
        job_width = max(20, self.size.width - _DATE_WIDTH - _STATE_WIDTH - _COL_PADDING)
        table.columns[self._job_col_key].width = job_width
        table.refresh()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        panel = self.query_one("#details-panel")
        if self._details_visible:
            panel.display = False
            self._details_visible = False
        else:
            self._show_details(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._details_visible:
            self._show_details(event.cursor_row)

    def _show_details(self, row: int) -> None:
        if row < 0 or row >= len(self._postings):
            return
        posting = self._postings[row]
        self.query_one("#details-content", Static).update(self._format_details(posting))
        self.query_one("#details-panel").display = True
        self._details_visible = True

    def action_prepare_job(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._postings):
            return
        posting = self._postings[row]
        if posting.status != "selected":
            self.notify("Only 'selected' jobs can be prepared", severity="warning")
            return

        prompt = (
            f"Use the job-preparer agent. A job is already in 'selected' state in the database "
            f"(URL: {posting.url}). Skip scoring and selection — go straight to running the full "
            f"pipeline (resume-tailor, rendercv, cover-letter-creator, rendercv) for this job."
        )

        output_widget = self.query_one("#output-content", Static)
        output_widget.update("")
        self.query_one("#output-panel").display = True
        self.notify(f"Launching prepare for {posting.company or posting.url}…")
        self._run_prepare(posting.url, prompt)

    @work(thread=True, exclusive=True)
    def _run_prepare(self, url: str, prompt: str) -> None:
        lines: list[str] = []

        def _update(line: str) -> None:
            lines.append(_ANSI_ESCAPE.sub("", line).rstrip())
            self.call_from_thread(
                self.query_one("#output-content", Static).update,
                "\n".join(lines),
            )

        try:
            proc = subprocess.Popen(
                ["claude", prompt],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            for line in proc.stdout:
                _update(line)
            proc.wait()
            if proc.returncode == 0:
                self.call_from_thread(self.notify, "Prepare complete!", severity="information")
            else:
                self.call_from_thread(
                    self.notify, f"Prepare failed (exit {proc.returncode})", severity="error"
                )
        except Exception as exc:
            self.call_from_thread(
                self.query_one("#output-content", Static).update, f"Error: {exc}"
            )
            self.call_from_thread(self.notify, f"Failed to launch claude: {exc}", severity="error")

    def action_toggle_output(self) -> None:
        panel = self.query_one("#output-panel")
        panel.display = not panel.display

    def action_mark_applied(self) -> None:
        from tui.db import make_engine, update_status

        table = self.query_one("#jobs-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._postings):
            return
        posting = self._postings[row]
        if posting.status == "applied":
            self.notify("Already marked as applied", severity="warning")
            return
        try:
            engine = make_engine(self.db_path)
            update_status(engine, posting.url, "applied")
        except Exception as e:
            self.notify(f"Failed to update status: {e}", severity="error")
            return
        posting.status = "applied"
        table.update_cell(
            posting.url,
            self._state_col_key,
            Text("applied", style=STATE_STYLES["applied"]),
            update_width=False,
        )
        self.notify(f"Marked as applied: {posting.display_name}")

    def action_scroll_details_down(self) -> None:
        if self._details_visible:
            self.query_one("#details-panel", ScrollableContainer).scroll_down()

    def action_scroll_details_up(self) -> None:
        if self._details_visible:
            self.query_one("#details-panel", ScrollableContainer).scroll_up()

    def _format_details(self, posting) -> str:
        lines: list[str] = []
        if posting.final_score is not None:
            modifier = posting.modifier or 0
            base = posting.base_score if posting.base_score is not None else "?"
            lines.append(
                f"Score:    {posting.final_score}"
                f"  (base {base}, modifier {modifier:+d})"
            )
        lines.append(f"Platform: {posting.platform or '—'}")
        lines.append(f"Location: {posting.location_note or '—'}")
        if posting.employment_type:
            lines.append(f"Type:     {posting.employment_type}")
        if posting.post_date:
            lines.append(f"Posted:   {posting.post_date}")
        if posting.applicant_count is not None:
            lines.append(f"Applicants: {posting.applicant_count}")
        lines.append(f"Status:   {posting.status or '—'}")
        if posting.description_summary:
            lines.extend(["", "Summary:", posting.description_summary])
        if posting.scoring_notes:
            lines.extend(["", "Scoring notes:", posting.scoring_notes])
        lines.extend(["", f"URL: {posting.url}"])
        return "\n".join(lines)
