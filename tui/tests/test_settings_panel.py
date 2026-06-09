"""Smoke + behavior tests for the TUI Settings panel via Textual's pilot.

Uses ``asyncio.run`` so no pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio

import pytest
from harness_db import config_store, disqualifiers, sources_store
from textual.widgets import DataTable

from tui.app import JobViewerApp
from tui.widgets import SettingsPanel


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "postings.db"))
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    config_store._engine_for.cache_clear()
    disqualifiers._engine_for.cache_clear()
    sources_store._engine.cache_clear()
    return tmp_path / "postings.db"


def test_settings_panel_mounts_and_loads(_isolate):
    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            app.query_one("#tabs").active = "settings"
            await pilot.pause()
            panel = app.query_one(SettingsPanel)
            assert panel.query_one("#sources-table", DataTable).row_count == 7

    asyncio.run(scenario())


def test_toggling_source_row_persists(_isolate):
    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            app.query_one("#tabs").active = "settings"
            await pilot.pause()
            panel = app.query_one(SettingsPanel)
            table = panel.query_one("#sources-table", DataTable)
            first_id = table.get_row_at(0)[1]
            before = first_id in sources_store.enabled_source_ids("default")
            table.focus()
            table.move_cursor(row=0)
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            after = first_id in sources_store.enabled_source_ids("default")
            assert before != after

    asyncio.run(scenario())


def test_switch_tab_cycles_through_settings(_isolate):
    """Pressing 't' must reach the Settings tab, not just toggle jobs/companies."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            tabs = app.query_one("#tabs")
            assert tabs.active == "jobs"
            await pilot.press("t")
            assert tabs.active == "companies"
            await pilot.press("t")
            assert tabs.active == "settings"
            await pilot.press("t")
            assert tabs.active == "jobs"

    asyncio.run(scenario())
