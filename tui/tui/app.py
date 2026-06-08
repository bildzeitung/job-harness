from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Header, TabbedContent, TabPane

from tui.widgets import CompanyPanel, JobsPanel, SettingsPanel


class JobViewerApp(App):
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("t", "switch_tab", "Switch Tab"),
    ]

    def __init__(self, db_path: Path, **kwargs) -> None:
        super().__init__(**kwargs)
        self.db_path = db_path
        self._engine = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs", initial="jobs"):
            with TabPane("Jobs", id="jobs"):
                yield JobsPanel(id="jobs-panel")
            with TabPane("Companies", id="companies"):
                yield CompanyPanel(id="company-panel")
            with TabPane("Settings", id="settings"):
                yield SettingsPanel(id="settings-panel")
        yield Footer()

    def on_mount(self) -> None:
        from tui.db import get_companies, get_postings, make_engine

        try:
            self._engine = make_engine(self.db_path)
            postings = get_postings(self._engine, self.query_one(JobsPanel).sort_by)
            companies = get_companies(self._engine)
        except Exception as e:
            self.exit(f"Error reading database: {e}")
            return

        self.query_one(JobsPanel).load(self._engine, postings)
        self.query_one(CompanyPanel).load(self._engine, companies)
        self._refresh_titles()
        self.query_one(JobsPanel).focus_table()

    def _refresh_titles(self) -> None:
        self.title = f"Job Viewer — {self.query_one(JobsPanel).count} postings"
        self.sub_title = f"{self.query_one(CompanyPanel).count} companies"

    def action_refresh(self) -> None:
        from tui.db import get_companies

        self.query_one(JobsPanel).reload()
        try:
            companies = get_companies(self._engine)
        except Exception as e:
            self.notify(f"Refresh failed: {e}", severity="error")
            return
        self.query_one(CompanyPanel).load(self._engine, companies)
        self._refresh_titles()

    def action_switch_tab(self) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        if tabs.active == "jobs":
            tabs.active = "companies"
            self.query_one(CompanyPanel).focus_table()
        else:
            tabs.active = "jobs"
            self.query_one(JobsPanel).focus_table()
