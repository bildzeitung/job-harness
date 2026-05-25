from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import ScrollableContainer, Vertical
from textual.widgets import DataTable, Footer, Header, Static

STATE_STYLES: dict[str, str] = {
    "new": "bold green",
    "scored": "bold cyan",
    "selected": "bold yellow",
    "skipped": "dim red",
    "applied": "bold red",
}

_DATE_WIDTH = 12
_STATE_WIDTH = 10
_COL_PADDING = 6  # borders, scrollbar, gutters


class JobViewerApp(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, db_path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db_path = db_path
        self._postings: list = []
        self._details_visible = False
        self._job_col_key = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="main"):
            yield DataTable(id="jobs-table", cursor_type="row", zebra_stripes=True)
            with ScrollableContainer(id="details-panel"):
                yield Static(id="details-content")
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
        table.add_column("State", width=_STATE_WIDTH)

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
