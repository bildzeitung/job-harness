"""Smoke + behavior tests for the TUI Settings panel via Textual's pilot.

Uses ``asyncio.run`` so no pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio

import pytest
from harness_db import config_store, disqualifiers, sources_store, users
from textual.widgets import DataTable, Input, TabbedContent

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


def test_entering_settings_focuses_a_control(_isolate):
    """Opening Settings must land focus on a real control, not leave it None."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # jobs -> companies -> settings
            assert app.query_one("#tabs").active == "settings"
            focused = app.focused
            assert focused is not None
            # Profile is the initial sub-tab; its first control is the users table.
            assert focused.id == "users-table"

    asyncio.run(scenario())


def test_switching_subtab_moves_focus_into_it(_isolate):
    """Selecting a different sub-tab should pull focus into its first control."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # into settings
            panel = app.query_one(SettingsPanel)
            panel.query_one("#settings-tabs", TabbedContent).active = "sources"
            await pilot.pause()
            assert app.focused is not None
            assert app.focused.id == "sources-table"

    asyncio.run(scenario())


def test_ctrl_a_adds_user_on_profile(_isolate):
    """Ctrl+A is the Add accelerator; on Profile it creates the typed user."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # into settings, Profile sub-tab
            panel = app.query_one(SettingsPanel)
            field = panel.query_one("#new-user-input", Input)
            field.focus()
            field.value = "alice"
            await pilot.pause()
            await pilot.press("ctrl+a")
            await pilot.pause()
            assert users.get_user(panel._engine, "alice") is not None

    asyncio.run(scenario())


def test_accelerators_inert_off_settings_tab(_isolate):
    """The Settings accelerators must not fire while another tab is visible."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            # Stay on the Jobs tab; pre-load a user id into the (hidden) field.
            panel = app.query_one(SettingsPanel)
            panel.query_one("#new-user-input", Input).value = "ghost"
            assert app.query_one("#tabs").active == "jobs"
            await pilot.press("ctrl+a")
            await pilot.pause()
            assert users.get_user(panel._engine, "ghost") is None

    asyncio.run(scenario())
