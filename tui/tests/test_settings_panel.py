"""Smoke + behavior tests for the TUI Settings panel via Textual's pilot.

Uses ``asyncio.run`` so no pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio

import pytest
from harness_db import config_store, disqualifiers, locales, sources_store, users
from textual.widgets import DataTable, Input, Select, TabbedContent, TabPane

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
    locales._engine_for.cache_clear()
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


def test_scoring_modifiers_have_their_own_subtab(_isolate):
    """Scoring modifiers must live in the 'scoring' sub-tab, not under 'disq'."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # jobs -> companies -> settings
            panel = app.query_one(SettingsPanel)
            scoring_pane = panel.query_one("#scoring", TabPane)
            disq_pane = panel.query_one("#disq", TabPane)
            # The scoring table belongs to the scoring pane only, not disq.
            assert scoring_pane.query("#scoring-table")
            assert not disq_pane.query("#scoring-table")
            # The scoring table is reachable once its sub-tab is active.
            panel.query_one("#settings-tabs", TabbedContent).active = "scoring"
            await pilot.pause()
            assert panel.query_one("#scoring-table", DataTable) is not None

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


def test_entering_settings_focuses_the_subtab_header(_isolate):
    """Opening Settings lands focus on the sub-tab header bar (not None and not
    a body control), so left/right arrows switch sub-tabs immediately."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # jobs -> companies -> settings
            assert app.query_one("#tabs").active == "settings"
            panel = app.query_one(SettingsPanel)
            assert app.focused is panel._tabs_header()

    asyncio.run(scenario())


def test_arrows_switch_subtabs_then_enter_descends(_isolate):
    """From the header, left/right switch sub-tabs without leaving the header;
    Enter descends into the active sub-tab's first control."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # into settings; header focused, Profile active
            panel = app.query_one(SettingsPanel)
            tabs = panel.query_one("#settings-tabs", TabbedContent)
            header = panel._tabs_header()
            assert tabs.active == "profile"
            # Right arrow advances the sub-tab; focus stays on the header.
            await pilot.press("right")
            await pilot.pause()
            assert tabs.active == "config"
            assert app.focused is header
            # Left arrow goes back.
            await pilot.press("left")
            await pilot.pause()
            assert tabs.active == "profile"
            assert app.focused is header
            # Enter descends into the active sub-tab's first control.
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused is not None
            assert app.focused.id == "users-table"

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


def test_add_custom_scoring_block(_isolate):
    """The Scoring sub-tab can add a custom modifier block (name + modifier)."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")  # into settings
            panel = app.query_one(SettingsPanel)
            panel.query_one("#settings-tabs", TabbedContent).active = "scoring"
            await pilot.pause()
            panel.query_one("#scoring-name", Input).value = "Hates Mondays"
            panel.query_one("#scoring-modifier", Input).value = "-15"
            panel.query_one("#scoring-examples", Input).value = "ex one, ex two"
            await pilot.pause()
            await pilot.press("ctrl+a")
            await pilot.pause()
            blocks = {b.name: b for b in disqualifiers.list_scoring_blocks("default")}
            assert "Hates Mondays" in blocks
            added = blocks["Hates Mondays"]
            assert added.modifier == -15
            assert added.custom is True
            assert added.examples == ["ex one", "ex two"]
            # The input fields are cleared after a successful add.
            assert panel.query_one("#scoring-name", Input).value == ""

    asyncio.run(scenario())


def test_add_scoring_block_rejects_non_integer_modifier(_isolate):
    """A non-integer modifier is rejected and no block is created."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.press("t")
            panel = app.query_one(SettingsPanel)
            panel.query_one("#settings-tabs", TabbedContent).active = "scoring"
            await pilot.pause()
            panel.query_one("#scoring-name", Input).value = "Bad"
            panel.query_one("#scoring-modifier", Input).value = "minus twenty"
            await pilot.pause()
            await pilot.press("ctrl+a")
            await pilot.pause()
            names = {b.name for b in disqualifiers.list_scoring_blocks("default")}
            assert "Bad" not in names

    asyncio.run(scenario())


def test_config_tab_renders_localized_labels(_isolate):
    """The Config sub-tab shows the en-US label + help text, not the raw key."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            app.query_one("#tabs").active = "settings"
            await pilot.pause()
            panel = app.query_one(SettingsPanel)
            panel.query_one("#settings-tabs", TabbedContent).active = "config"
            await pilot.pause()
            label_text = [str(lbl.content) for lbl in panel.query("#config-fields Label")]
            assert "Resume file" in label_text  # humanized RESUME_FILE label
            assert "RESUME_FILE" not in label_text
            help_text = [str(s.content) for s in panel.query(".config-help")]
            assert any("RenderCV" in h for h in help_text)

    asyncio.run(scenario())


def test_locale_selector_populated_and_persists(_isolate):
    """The Profile locale picker lists seeded locales and persists a change."""

    async def scenario():
        app = JobViewerApp(db_path=_isolate)
        async with app.run_test() as pilot:
            app.query_one("#tabs").active = "settings"
            await pilot.pause()
            panel = app.query_one(SettingsPanel)
            select = panel.query_one("#locale-select", Select)
            assert select.value == "en-US"
            # Selecting a known locale persists it for the active user.
            select.value = "en-US"
            await pilot.pause()
            assert locales.get_user_locale("default") == "en-US"

    asyncio.run(scenario())
