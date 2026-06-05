from __future__ import annotations

from harness_db.agent_io import REJECTABLE_STATES, build_prepare_prompt, build_score_command
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from tui.widgets.scorer_panel import ScorerPanel

STATE_STYLES: dict[str, str] = {
    "new": "bold green",
    "scored": "bold cyan",
    "selected": "bold yellow",
    "skipped": "dim red",
    "rejected": "dim red",
    "prepared": "bold magenta",
    "applied": "bold red",
}

_SCORE_WIDTH = 7
_DATE_WIDTH = 12
_STATE_WIDTH = 10
_COL_PADDING = 6  # borders, scrollbar, gutters
_FIXED_COLS_WIDTH = _SCORE_WIDTH + _DATE_WIDTH + _STATE_WIDTH + _COL_PADDING
_MIN_JOB_WIDTH = 20

_SORT_MODES = ["state", "date", "title"]
_SORT_INDICATOR = "▼"


class JobsPanel(Widget):
    """Jobs tab: table, detail popup, scorer output panel + jobs-specific actions."""

    BINDINGS = [
        Binding("s", "cycle_sort", "Sort"),
        Binding("p", "prepare_job", "Prepare"),
        Binding("a", "mark_applied", "Applied"),
        Binding("x", "mark_rejected", "Reject"),
        Binding("S", "score_new", "Score New"),
        Binding("o", "toggle_output", "Output", show=True),
        Binding("j", "scroll_details_down", "Scroll ↓", show=False),
        Binding("k", "scroll_details_up", "Scroll ↑", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._engine = None
        self._postings: list = []
        self._sort_by = "state"
        self._details_visible = False
        self._score_col_key = None
        self._job_col_key = None
        self._date_col_key = None
        self._state_col_key = None

    def compose(self) -> ComposeResult:
        with Vertical(id="jobs-pane"):
            yield DataTable(id="jobs-table", cursor_type="row", zebra_stripes=True)
            with ScrollableContainer(id="details-panel"):
                yield Static(id="details-content")
            yield ScorerPanel(id="output-panel")

    def on_mount(self) -> None:
        self.query_one("#details-panel").display = False
        self.query_one("#output-panel").display = False

    def load(self, engine, postings: list) -> None:
        self._engine = engine
        self._postings = postings
        self._init_table()
        self.query_one("#details-panel").display = False
        self._details_visible = False

    def reload(self) -> None:
        from tui.db import get_postings

        try:
            self._postings = get_postings(self._engine, self._sort_by)
        except Exception as e:
            self.app.notify(f"Refresh failed: {e}", severity="error")
            return
        self._init_table()
        self.query_one("#details-panel").display = False
        self._details_visible = False

    @property
    def count(self) -> int:
        return len(self._postings)

    @property
    def sort_by(self) -> str:
        return self._sort_by

    def focus_table(self) -> None:
        self.query_one("#jobs-table", DataTable).focus()

    def _col_label(self, label: str, sort_key: str) -> str:
        if self._sort_by == sort_key:
            return f"{label} {_SORT_INDICATOR}"
        return label

    def _job_width(self) -> int:
        return max(_MIN_JOB_WIDTH, self.size.width - _FIXED_COLS_WIDTH)

    @staticmethod
    def _score_cell(posting) -> Text:
        if posting.final_score is None:
            return Text("—", style="dim", justify="right")
        return Text(str(posting.final_score), justify="right")

    def _init_table(self) -> None:
        table = self.query_one("#jobs-table", DataTable)
        table.clear(columns=True)
        self._score_col_key = table.add_column("Score", width=_SCORE_WIDTH)
        self._job_col_key = table.add_column(
            self._col_label("Job", "title"), width=self._job_width()
        )
        self._date_col_key = table.add_column(self._col_label("Date", "date"), width=_DATE_WIDTH)
        self._state_col_key = table.add_column(
            self._col_label("State", "state"), width=_STATE_WIDTH
        )

        for posting in self._postings:
            status = posting.status or "new"
            table.add_row(
                self._score_cell(posting),
                posting.display_name,
                posting.display_date,
                Text(status, style=STATE_STYLES.get(status, "white")),
                key=posting.url,
            )

    def on_resize(self) -> None:
        if self._job_col_key is None:
            return
        table = self.query_one("#jobs-table", DataTable)
        table.columns[self._job_col_key].width = self._job_width()
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
        event.stop()

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

    def _cursor_posting(self):
        table = self.query_one("#jobs-table", DataTable)
        row = table.cursor_row
        if row < 0 or row >= len(self._postings):
            return None
        return self._postings[row]

    def action_cycle_sort(self) -> None:
        idx = (_SORT_MODES.index(self._sort_by) + 1) % len(_SORT_MODES)
        self._sort_by = _SORT_MODES[idx]
        self.reload()
        self.app.notify(f"Sorted by: {self._sort_by}", timeout=2)

    def action_prepare_job(self) -> None:
        posting = self._cursor_posting()
        if posting is None:
            return
        if posting.status != "selected":
            self.app.notify("Only 'selected' jobs can be prepared", severity="warning")
            return
        prompt = build_prepare_prompt(posting)
        panel = self.query_one("#output-panel", ScorerPanel)
        panel.display = True
        self.app.notify(f"Launching prepare for {posting.company or posting.url}…")
        panel.run_prompt(prompt)

    def action_score_new(self) -> None:
        posting = self._cursor_posting()
        if posting is None:
            return
        if posting.status != "new":
            self.app.notify(
                f"Only 'new' jobs can be scored (this job is '{posting.status}')",
                severity="warning",
            )
            return
        argv = build_score_command(posting)
        panel = self.query_one("#output-panel", ScorerPanel)
        panel.display = True
        self.app.notify(f"Scoring {posting.display_name}…")
        panel.run_command(argv)

    def action_toggle_output(self) -> None:
        panel = self.query_one("#output-panel")
        panel.display = not panel.display

    def action_mark_applied(self) -> None:
        self._update_posting_status(
            "applied", lambda p: p.status != "applied", "Already marked as applied"
        )

    def action_mark_rejected(self) -> None:
        self._update_posting_status(
            "rejected",
            lambda p: (p.status or "new") in REJECTABLE_STATES,
            f"Only {sorted(REJECTABLE_STATES)} jobs can be rejected",
        )

    def _update_posting_status(self, new_status: str, allowed, warn_msg: str) -> None:
        from tui.db import update_status

        posting = self._cursor_posting()
        if posting is None:
            return
        if not allowed(posting):
            self.app.notify(warn_msg, severity="warning")
            return
        try:
            update_status(self._engine, posting.url, new_status)
        except Exception as e:
            self.app.notify(f"Failed to update status: {e}", severity="error")
            return
        posting.status = new_status
        table = self.query_one("#jobs-table", DataTable)
        table.update_cell(
            posting.url,
            self._state_col_key,
            Text(new_status, style=STATE_STYLES.get(new_status, "white")),
            update_width=False,
        )
        self.app.notify(f"Marked as {new_status}: {posting.display_name}")

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
            lines.append(f"Score:    {posting.final_score}  (base {base}, modifier {modifier:+d})")
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
