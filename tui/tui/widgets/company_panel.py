from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer, Vertical
from textual.widget import Widget
from textual.widgets import DataTable, Static

from tui.db import get_company_postings

# Cap the per-company job list in the detail popup so a prolific employer
# doesn't blow up the panel; the rest are summarized as "… and N more".
_MAX_LISTED_POSTINGS = 25


def _bool_glyph(value: bool | None) -> str:
    if value is True:
        return "✓"
    if value is False:
        return "✗"
    return "—"


class CompanyPanel(Widget):
    """Companies tab: data table + toggleable detail popup."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._engine = None
        self._companies: list = []
        self._details_visible = False

    def compose(self) -> ComposeResult:
        with Vertical(id="companies-pane"):
            yield DataTable(id="companies-table", cursor_type="row", zebra_stripes=True)
            with ScrollableContainer(id="company-details-panel"):
                yield Static(id="company-details-content")

    def on_mount(self) -> None:
        self.query_one("#company-details-panel").display = False

    def load(self, engine, companies: list) -> None:
        self._engine = engine
        self._companies = companies
        table = self.query_one("#companies-table", DataTable)
        table.clear(columns=True)
        table.add_column("Company", width=30)
        table.add_column("Remote", width=8)
        table.add_column("Canada", width=8)
        table.add_column("Last Seen", width=12)
        table.add_column("Notes")

        for company in companies:
            last_seen = (company.last_seen_date or "—")[:10]
            table.add_row(
                company.name or "—",
                _bool_glyph(company.remote_confirmed),
                _bool_glyph(company.canada_confirmed),
                last_seen,
                company.notes or "—",
                key=company.name,
            )

        self.query_one("#company-details-panel").display = False
        self._details_visible = False

    @property
    def count(self) -> int:
        return len(self._companies)

    def focus_table(self) -> None:
        self.query_one("#companies-table", DataTable).focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.control.id != "companies-table":
            return
        if self._details_visible:
            self.query_one("#company-details-panel").display = False
            self._details_visible = False
        else:
            self._show_details(event.cursor_row)
        event.stop()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.control.id != "companies-table":
            return
        if self._details_visible:
            self._show_details(event.cursor_row)

    def _show_details(self, row: int) -> None:
        if row < 0 or row >= len(self._companies):
            return
        company = self._companies[row]
        self.query_one("#company-details-content", Static).update(self._format_details(company))
        self.query_one("#company-details-panel").display = True
        self._details_visible = True

    def _format_details(self, company) -> str:
        lines: list[str] = [f"Company:  {company.name or '—'}"]
        lines.append(f"Remote:   {_bool_glyph(company.remote_confirmed)}")
        lines.append(f"Canada:   {_bool_glyph(company.canada_confirmed)}")
        if company.last_seen_date:
            lines.append(f"Last seen: {company.last_seen_date[:10]}")
        if company.researched_date:
            lines.append(f"Researched: {company.researched_date[:10]}")
        if company.careers_url:
            lines.append(f"Careers:  {company.careers_url}")
        if company.notes:
            lines.extend(["", "Notes:", company.notes])
        if company.fetch_notes:
            lines.extend(["", "Fetch notes:", company.fetch_notes])
        lines.extend(self._listing_lines(company))
        return "\n".join(lines)

    def _listing_lines(self, company) -> list[str]:
        if self._engine is None or not company.name:
            return []
        postings = get_company_postings(self._engine, company.name)
        if not postings:
            return ["", "Job listings: none"]
        lines = ["", f"Job listings ({len(postings)}):"]
        for p in postings[:_MAX_LISTED_POSTINGS]:
            score = p.final_score if p.final_score is not None else "—"
            status = p.status or "new"
            lines.append(f"  [{score:>3}] {status:<9} {p.title or p.url}")
        if len(postings) > _MAX_LISTED_POSTINGS:
            lines.append(f"  … and {len(postings) - _MAX_LISTED_POSTINGS} more")
        return lines
