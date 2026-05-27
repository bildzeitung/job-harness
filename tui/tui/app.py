from __future__ import annotations

import re
import subprocess
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane
from textual import work
from textual.worker import get_current_worker

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
_ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

_SORT_MODES = ["state", "date", "title"]
_SORT_INDICATOR = "▼"


class JobViewerApp(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("s", "cycle_sort", "Sort"),
        Binding("t", "switch_tab", "Switch Tab"),
        Binding("p", "prepare_job", "Prepare"),
        Binding("a", "mark_applied", "Applied"),
        Binding("S", "score_new", "Score New"),
        Binding("o", "toggle_output", "Output", show=False),
        Binding("j", "scroll_details_down", "Scroll ↓", show=False),
        Binding("k", "scroll_details_up", "Scroll ↑", show=False),
    ]

    def __init__(self, db_path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db_path = db_path
        self._engine = None
        self._postings: list = []
        self._companies: list = []
        self._details_visible = False
        self._sort_by = "state"
        self._job_col_key = None
        self._date_col_key = None
        self._state_col_key = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs", initial="jobs"):
            with TabPane("Jobs", id="jobs"):
                with Vertical(id="jobs-pane"):
                    yield DataTable(id="jobs-table", cursor_type="row", zebra_stripes=True)
                    with ScrollableContainer(id="details-panel"):
                        yield Static(id="details-content")
                    with ScrollableContainer(id="output-panel"):
                        yield Static(id="output-content")
            with TabPane("Companies", id="companies"):
                yield DataTable(id="companies-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        from tui.db import get_companies, get_postings, make_engine

        try:
            self._engine = make_engine(self.db_path)
            self._postings = get_postings(self._engine, self._sort_by)
            self._companies = get_companies(self._engine)
        except Exception as e:
            self.exit(f"Error reading database: {e}")
            return

        self._init_jobs_table()
        self._init_companies_table()

        self.query_one("#details-panel").display = False
        self.query_one("#output-panel").display = False
        self.query_one("#jobs-table", DataTable).focus()

    def _col_label(self, label: str, sort_key: str) -> str:
        if self._sort_by == sort_key:
            return f"{label} {_SORT_INDICATOR}"
        return label

    def _init_jobs_table(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear(columns=True)
        job_width = max(20, self.size.width - _DATE_WIDTH - _STATE_WIDTH - _COL_PADDING)
        self._job_col_key = table.add_column(self._col_label("Job", "title"), width=job_width)
        self._date_col_key = table.add_column(self._col_label("Date", "date"), width=_DATE_WIDTH)
        self._state_col_key = table.add_column(self._col_label("State", "state"), width=_STATE_WIDTH)

        for posting in self._postings:
            status = posting.status or "new"
            table.add_row(
                posting.display_name,
                posting.display_date,
                Text(status, style=STATE_STYLES.get(status, "white")),
                key=posting.url,
            )

        self.title = f"Job Viewer — {len(self._postings)} postings"

    def _init_companies_table(self) -> None:
        table = self.query_one("#companies-table", DataTable)
        table.clear(columns=True)
        table.add_column("Company", width=30)
        table.add_column("Remote", width=8)
        table.add_column("Canada", width=8)
        table.add_column("Last Seen", width=12)
        table.add_column("Notes")

        for company in self._companies:
            remote = "✓" if company.remote_confirmed else ("✗" if company.remote_confirmed is False else "—")
            canada = "✓" if company.canada_confirmed else ("✗" if company.canada_confirmed is False else "—")
            last_seen = (company.last_seen_date or "—")[:10]
            table.add_row(
                company.name or "—",
                remote,
                canada,
                last_seen,
                company.notes or "—",
                key=company.name,
            )

        self.sub_title = f"{len(self._companies)} companies"

    def action_refresh(self) -> None:
        from tui.db import get_companies, get_postings

        try:
            self._postings = get_postings(self._engine, self._sort_by)
            self._companies = get_companies(self._engine)
        except Exception as e:
            self.notify(f"Refresh failed: {e}", severity="error")
            return

        self._init_jobs_table()
        self._init_companies_table()
        self.query_one("#details-panel").display = False
        self._details_visible = False

    def action_cycle_sort(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active != "jobs":
            return
        idx = (_SORT_MODES.index(self._sort_by) + 1) % len(_SORT_MODES)
        self._sort_by = _SORT_MODES[idx]
        from tui.db import get_postings
        try:
            self._postings = get_postings(self._engine, self._sort_by)
        except Exception as e:
            self.notify(f"Sort failed: {e}", severity="error")
            return
        self._init_jobs_table()
        self.query_one("#details-panel").display = False
        self._details_visible = False
        self.notify(f"Sorted by: {self._sort_by}", timeout=2)

    def action_switch_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active == "jobs":
            tabs.active = "companies"
            self.query_one("#companies-table", DataTable).focus()
        else:
            tabs.active = "jobs"
            self.query_one("#jobs-table", DataTable).focus()

    def on_resize(self) -> None:
        if self._job_col_key is None:
            return
        table = self.query_one("#jobs-table", DataTable)
        job_width = max(20, self.size.width - _DATE_WIDTH - _STATE_WIDTH - _COL_PADDING)
        table.columns[self._job_col_key].width = job_width
        table.refresh()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "jobs-table":
            return
        panel = self.query_one("#details-panel")
        if self._details_visible:
            panel.display = False
            self._details_visible = False
        else:
            self._show_details(event.cursor_row)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.control.id != "jobs-table":
            return
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
        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active != "jobs":
            return
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

        output = self.query_one("#output-content", Static)
        output.update("")
        self.query_one("#output-panel").display = True
        self.notify(f"Launching prepare for {posting.company or posting.url}…")
        self._run_claude(prompt, output)

    def action_score_new(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active != "jobs":
            return
        table = self.query_one("#jobs-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._postings):
            return
        posting = self._postings[row]
        if posting.status != "new":
            self.notify(f"Only 'new' jobs can be scored (this job is '{posting.status}')", severity="warning")
            return
        prompt = (
            f"Use the job-scorer agent to score a single job posting. "
            f"The posting URL is: {posting.url}\n"
            f"Company: {posting.company or 'unknown'}\n"
            f"Title: {posting.title or 'unknown'}\n"
            f"Score this one posting only. Write the score to the database and set status to 'scored'."
        )
        output = self.query_one("#output-content", Static)
        output.update("")
        self.query_one("#output-panel").display = True
        self.notify(f"Scoring {posting.display_name}…")
        self._run_claude(prompt, output)

    @work(thread=True, exclusive=True)
    def _run_claude(self, prompt: str, output: Static) -> None:
        import os
        import pty
        import select as _select

        lines: list[str] = []
        self.call_from_thread(output.update, Text("Launching…"))

        def _flush_line(raw: str) -> None:
            text = _ANSI_ESCAPE.sub("", raw).rstrip()
            if text:
                lines.append(text)
                self.call_from_thread(output.update, Text("\n".join(lines)))

        master_fd, slave_fd = pty.openpty()
        try:
            proc = subprocess.Popen(
                ["claude", "--print", prompt],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                preexec_fn=os.setsid,
                env={**os.environ, "TERM": "dumb", "NO_COLOR": "1"},
            )
        except Exception as exc:
            os.close(master_fd)
            self.call_from_thread(output.update, Text(f"Error launching claude: {exc}"))
            self.call_from_thread(self.notify, f"Launch failed: {exc}", severity="error")
            return
        finally:
            os.close(slave_fd)

        buf : str = ""
        worker = get_current_worker()
        try:
            # Keep reading while the process lives and the app hasn't cancelled the worker
            while proc.poll() is None and not worker.is_cancelled:
                # 4. Use select() to wait up to 0.1 seconds for data to become available.
                # This prevents os.read from blocking the thread indefinitely if the process is idle.
                ready_to_read, _, _ = _select.select([master_fd], [], [], 0.05)
                
                if ready_to_read:
                    # Data is waiting in the OS buffer, safe to read without blocking
                    chunk = os.read(master_fd, 4096).decode(encoding="utf-8", errors="replace")
                    if not chunk:
                        break  # Stream reached End-Of-File (EOF)

                    text = buf + chunk
                    text = text.replace("\r\n", "\n").replace("\r", "\n")
                    parts = text.split("\n")
                    for part in parts[:-1]:
                        _flush_line(part)
                    buf = parts[-1]
        except OSError:
            # Raised by os.read when the PTY closes down completely
            pass
        finally:
            # 5. Clean up the master file descriptor and terminate if stopped early
            os.close(master_fd)
            if proc.poll() is None:
                proc.terminate()

        if proc.returncode == 0:
            self.call_from_thread(self.notify, "Done!", severity="information")
        else:
            self.call_from_thread(
                self.notify, f"Failed (exit {proc.returncode})", severity="error"
            )

    def action_toggle_output(self) -> None:
        panel = self.query_one("#output-panel")
        panel.display = not panel.display

    def action_mark_applied(self) -> None:
        from tui.db import update_status

        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active != "jobs":
            return
        table = self.query_one("#jobs-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._postings):
            return
        posting = self._postings[row]
        if posting.status == "applied":
            self.notify("Already marked as applied", severity="warning")
            return
        try:
            update_status(self._engine, posting.url, "applied")
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
