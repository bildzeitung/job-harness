"""Reflex application state: data loading, selection, status changes, agent runs."""

from __future__ import annotations

import reflex as rx
from harness_db.agent_io import REJECTABLE_STATES, build_prepare_prompt, build_score_command

from web import data
from web.runner import stream_agent, stream_command
from web.theme import DEFAULT_SORT
from web.view_models import CompanyVM, PostingVM

_APPLIED = "applied"
_REJECTED = "rejected"
_SELECTED = "selected"
_NEW = "new"
_LAUNCHING_MSG = "Launching…"


class AppState(rx.State):
    postings: list[PostingVM] = []
    companies: list[CompanyVM] = []
    sort_by: str = DEFAULT_SORT
    error: str = ""

    # Selected-row detail panel.
    selected_url: str = ""
    selected_name: str = ""
    selected_detail: str = ""
    selected_status: str = ""
    detail_open: bool = False

    # Selected-company detail panel.
    company_name: str = ""
    company_detail: str = ""
    company_detail_open: bool = False

    # Agent output panel.
    scorer_open: bool = False
    scorer_running: bool = False
    scorer_lines: list[str] = []

    @rx.var
    def posting_count(self) -> int:
        return len(self.postings)

    @rx.var
    def company_count(self) -> int:
        return len(self.companies)

    @rx.var
    def can_score(self) -> bool:
        return self.selected_status == _NEW

    @rx.var
    def can_prepare(self) -> bool:
        return self.selected_status == _SELECTED

    @rx.var
    def can_apply(self) -> bool:
        return bool(self.selected_url) and self.selected_status != _APPLIED

    @rx.var
    def can_reject(self) -> bool:
        return self.selected_status in REJECTABLE_STATES

    # --- loading -------------------------------------------------------------

    def load(self):
        self._reload_all()

    def _reload_all(self):
        try:
            self.postings = data.load_postings(self.sort_by)
            self.companies = data.load_companies()
            self.error = ""
        except Exception as exc:
            self.error = f"Error reading database: {exc}"

    def _reload_postings(self):
        try:
            self.postings = data.load_postings(self.sort_by)
            self.error = ""
        except Exception as exc:
            self.error = f"Error reading database: {exc}"

    def refresh(self):
        self._reload_all()
        self._sync_selection()

    def set_sort(self, value: str):
        self.sort_by = value
        self._reload_postings()

    # --- selection -----------------------------------------------------------

    def select_row(self, url: str):
        if self.detail_open and self.selected_url == url:
            self.detail_open = False
            return
        for p in self.postings:
            if p.url == url:
                self.selected_url = p.url
                self.selected_name = p.display_name
                self.selected_detail = p.detail_text
                self.selected_status = p.status
                self.detail_open = True
                return

    def _sync_selection(self):
        """After a reload, refresh the open detail panel from new data."""
        if not self.selected_url:
            return
        for p in self.postings:
            if p.url == self.selected_url:
                self.selected_name = p.display_name
                self.selected_detail = p.detail_text
                self.selected_status = p.status
                return

    def _find(self, url: str) -> PostingVM | None:
        for p in self.postings:
            if p.url == url:
                return p
        return None

    def select_company(self, name: str):
        if self.company_detail_open and self.company_name == name:
            self.company_detail_open = False
            return
        for c in self.companies:
            if c.name == name:
                self.company_name = c.name
                self.company_detail = c.detail_text
                self.company_detail_open = True
                return

    # --- status changes ------------------------------------------------------

    def mark_applied(self):
        self._change_status(
            self.selected_url, _APPLIED, lambda p: p.status != _APPLIED, "Already marked as applied"
        )

    def mark_rejected(self):
        self._change_status(
            self.selected_url,
            _REJECTED,
            lambda p: p.status in REJECTABLE_STATES,
            f"Only {sorted(REJECTABLE_STATES)} jobs can be rejected",
        )

    def _change_status(self, url, new_status, allowed, warn_msg):
        vm = self._find(url)
        if vm is None:
            return
        if not allowed(vm):
            self.error = warn_msg
            return
        try:
            data.set_status(url, new_status)
        except Exception as exc:
            self.error = f"Failed to update status: {exc}"
            return
        self.error = ""
        self._reload_postings()
        self._sync_selection()

    # --- agent runs ----------------------------------------------------------

    @rx.event(background=True)
    async def score_new(self):
        async with self:
            vm = self._find(self.selected_url)
            if vm is None or vm.status != _NEW:
                self.error = "Only 'new' jobs can be scored"
                return
            argv = build_score_command(vm)
        await self._run_stream(stream_command(argv))

    @rx.event(background=True)
    async def prepare(self):
        async with self:
            vm = self._find(self.selected_url)
            if vm is None or vm.status != _SELECTED:
                self.error = "Only 'selected' jobs can be prepared"
                return
            prompt = build_prepare_prompt(vm)
        await self._run_stream(stream_agent(prompt))

    async def _run_stream(self, lines):
        # In a background task, each `async with self` block flushes a delta to the
        # browser, so the log streams live as lines arrive. `lines` is the async
        # iterator from stream_agent (prepare) or stream_command (score).
        async with self:
            self.error = ""
            self.scorer_open = True
            self.scorer_running = True
            self.scorer_lines = [_LAUNCHING_MSG]
        async for line in lines:
            async with self:
                self.scorer_lines.append(line)
        async with self:
            self.scorer_running = False
            self._reload_postings()
            self._sync_selection()

    def toggle_scorer(self):
        self.scorer_open = not self.scorer_open
