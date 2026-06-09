"""Settings tab: user profile, config values, sources, disqualifiers, target roles.

Every action goes through the shared ``harness_db`` libraries (the same code path
the web UI uses), so the TUI and web stay in sync with the DB.
"""

from __future__ import annotations

from harness_db import config_store, disqualifiers, sources_store, target_roles, users
from harness_db.config import get_active_uid, set_active_uid
from harness_db.disqualifiers import PREFILTER_CATEGORIES
from harness_db.seed import ensure_schema_and_seed
from harness_db.target_roles import KINDS
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)


def _glyph(enabled: bool) -> str:
    return "✓" if enabled else " "


class SettingsPanel(Widget):
    """Container of settings sub-tabs, all backed by the harness DB."""

    # Accelerators for the action buttons. priority=True lets them win over a
    # focused Input (which would otherwise eat e.g. ctrl+a for line editing), so
    # you can type in a field and fire the button without tabbing away. They are
    # always live on this (always-composed) panel, so check_action() gates them:
    # active only while Settings is the visible tab and the relevant sub-tab is
    # current. "Add"/"Delete" are context-aware — they dispatch to whichever
    # sub-tab is active. show=False keeps the footer uncluttered; the underlined
    # letter in each button label advertises the key instead.
    BINDINGS = [
        Binding("ctrl+a", "settings_add", "Add", show=False, priority=True),
        Binding("ctrl+d", "settings_delete", "Delete custom", show=False, priority=True),
        Binding("ctrl+k", "make_active", "Make active", show=False, priority=True),
        Binding("ctrl+t", "toggle_active_flag", "Toggle active flag", show=False, priority=True),
        Binding("ctrl+s", "save_config", "Save config", show=False, priority=True),
    ]

    # Which sub-tab(s) each accelerator action applies to.
    _ACTION_SUBTABS = {
        "settings_add": {"profile", "disq", "scoring", "roles"},
        "settings_delete": {"disq", "scoring", "roles"},
        "make_active": {"profile"},
        "toggle_active_flag": {"profile"},
        "save_config": {"config"},
    }

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._engine = None
        self._uid = ""

    # --- compose -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with TabbedContent(id="settings-tabs", initial="profile"):
            with TabPane("Profile", id="profile"):
                yield from self._compose_profile()
            with TabPane("Config", id="config"):
                yield from self._compose_config()
            with TabPane("Sources", id="sources"):
                yield from self._compose_sources()
            with TabPane("Disqualifiers", id="disq"):
                yield from self._compose_disq()
            with TabPane("Scoring", id="scoring"):
                yield from self._compose_scoring()
            with TabPane("Target Roles", id="roles"):
                yield from self._compose_roles()

    def _compose_profile(self) -> ComposeResult:
        with Vertical():
            yield Static(id="active-user-label")
            yield DataTable(id="users-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Input(placeholder="new user id", id="new-user-input")
                yield Button("[u]A[/u]dd user", id="add-user-btn", variant="primary")
                yield Button("Ma[u]k[/u]e active", id="use-user-btn")
                yield Button("[u]T[/u]oggle active flag", id="toggle-user-btn")

    def _compose_config(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Per-user config (blank inherits the env/settings fallback):")
            yield Vertical(id="config-fields")
            yield Button("[u]S[/u]ave config", id="save-config-btn", variant="primary")

    def _compose_sources(self) -> ComposeResult:
        with Vertical():
            yield Static("Enter toggles a source on/off for the active user.")
            yield DataTable(id="sources-table", cursor_type="row", zebra_stripes=True)

    def _compose_disq(self) -> ComposeResult:
        with Vertical():
            yield Static("Prefilter — Enter toggles; '*' = custom. ")
            yield DataTable(id="prefilter-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Select(
                    [(c, c) for c in PREFILTER_CATEGORIES],
                    id="prefilter-category",
                    prompt="category",
                )
                yield Input(placeholder="keyword / phrase", id="prefilter-value")
                yield Button("[u]A[/u]dd", id="add-prefilter-btn", variant="primary")
                yield Button("[u]D[/u]elete custom", id="del-prefilter-btn", variant="error")

    def _compose_scoring(self) -> ComposeResult:
        with Vertical():
            yield Static("Scoring modifiers — Enter toggles; '*' = custom.")
            yield DataTable(id="scoring-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Input(placeholder="block name", id="scoring-name")
                yield Input(placeholder="modifier (e.g. -20)", id="scoring-modifier")
                yield Input(placeholder="examples (comma-separated)", id="scoring-examples")
                yield Button("[u]A[/u]dd", id="add-scoring-btn", variant="primary")
                yield Button("[u]D[/u]elete custom", id="del-scoring-btn", variant="error")

    def _compose_roles(self) -> ComposeResult:
        with Vertical():
            yield Static("Target roles — Enter toggles; '*' = custom.")
            yield DataTable(id="roles-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Select([(k, k) for k in KINDS], id="role-kind", prompt="kind")
                yield Input(placeholder="title / keyword / domain", id="role-value")
                yield Button("[u]A[/u]dd", id="add-role-btn", variant="primary")
                yield Button("[u]D[/u]elete custom", id="del-role-btn", variant="error")

    # --- lifecycle -----------------------------------------------------------

    def on_mount(self) -> None:
        self._engine = ensure_schema_and_seed()
        self.reload()

    def reload(self) -> None:
        self._uid = get_active_uid()
        self._load_users()
        self._load_config()
        self._load_sources()
        self._load_disq()
        self._load_scoring()
        self._load_roles()

    # --- keyboard focus ------------------------------------------------------

    # First control to land on for each sub-tab (config is handled separately
    # because its inputs are mounted dynamically).
    _SUBTAB_FOCUS = {
        "profile": "#users-table",
        "sources": "#sources-table",
        "disq": "#prefilter-table",
        "scoring": "#scoring-table",
        "roles": "#roles-table",
    }

    def focus_first(self) -> None:
        """Move keyboard focus into the active sub-tab's first control.

        Called when the Settings tab is opened so the user lands on a real
        control (Textual otherwise leaves focus at ``None`` here) and can
        immediately use arrows / Tab / the button accelerators.
        """
        self._focus_active_subtab()

    def _focus_active_subtab(self) -> None:
        active = self.query_one("#settings-tabs", TabbedContent).active
        target: Widget | None = None
        if active == "config":
            inputs = self.query("#config-fields Input")
            target = inputs.first() if inputs else self.query_one("#save-config-btn", Button)
        elif active in self._SUBTAB_FOCUS:
            target = self.query_one(self._SUBTAB_FOCUS[active], DataTable)
        if target is not None:
            target.focus()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Follow the user into a newly selected sub-tab's controls.

        Only the inner (#settings-tabs) switcher is handled, and only while the
        Settings tab is the visible outer tab — otherwise the initial activation
        during compose would steal focus from the Jobs table at startup.
        """
        if event.tabbed_content is not self.query_one("#settings-tabs", TabbedContent):
            return
        try:
            if self.app.query_one("#tabs", TabbedContent).active != "settings":
                return
        except Exception:
            return
        self._focus_active_subtab()
        event.stop()

    # --- profile -------------------------------------------------------------

    def _load_users(self) -> None:
        self.query_one("#active-user-label", Static).update(f"Active user: [b]{self._uid}[/b]")
        table = self.query_one("#users-table", DataTable)
        table.clear(columns=True)
        table.add_column("", width=3)
        table.add_column("User", width=24)
        table.add_column("Active flag", width=12)
        for u in users.list_users(self._engine):
            current = "→" if u.uid == self._uid else ""
            table.add_row(current, u.uid, "active" if u.active else "inactive", key=u.uid)

    def _highlighted_user(self) -> str | None:
        table = self.query_one("#users-table", DataTable)
        if table.row_count == 0:
            return None
        try:
            return table.get_row_at(table.cursor_row)[1]
        except Exception:
            return None

    # --- config --------------------------------------------------------------

    def _load_config(self) -> None:
        container = self.query_one("#config-fields", Vertical)
        container.remove_children()
        for key, value in config_store.list_config(self._uid).items():
            container.mount(Label(key))
            container.mount(Input(value=value or "", id=f"cfg-{key}"))

    # --- sources -------------------------------------------------------------

    def _load_sources(self) -> None:
        table = self.query_one("#sources-table", DataTable)
        table.clear(columns=True)
        table.add_column("On", width=4)
        table.add_column("Source", width=14)
        table.add_column("Description")
        for s in sources_store.list_sources(self._uid):
            table.add_row(_glyph(s.enabled), s.source_id, s.description, key=s.source_id)

    # --- disqualifiers -------------------------------------------------------

    def _load_disq(self) -> None:
        pt = self.query_one("#prefilter-table", DataTable)
        pt.clear(columns=True)
        pt.add_column("On", width=4)
        pt.add_column("Category", width=26)
        pt.add_column("Value")
        for r in disqualifiers.list_prefilter_rules(self._uid):
            value = f"{r.value} *" if r.custom else r.value
            pt.add_row(_glyph(r.enabled), r.category, value, key=str(r.id))

    # --- scoring modifiers ---------------------------------------------------

    def _load_scoring(self) -> None:
        st = self.query_one("#scoring-table", DataTable)
        st.clear(columns=True)
        st.add_column("On", width=4)
        st.add_column("Mod", width=6)
        st.add_column("Block")
        for b in disqualifiers.list_scoring_blocks(self._uid):
            name = f"{b.name} *" if b.custom else b.name
            st.add_row(_glyph(b.enabled), str(b.modifier), name, key=str(b.id))

    # --- roles ---------------------------------------------------------------

    def _load_roles(self) -> None:
        table = self.query_one("#roles-table", DataTable)
        table.clear(columns=True)
        table.add_column("On", width=4)
        table.add_column("Kind", width=10)
        table.add_column("Value")
        for i in target_roles.list_target_roles(self._uid):
            value = f"{i.value} *" if i.custom else i.value
            table.add_row(_glyph(i.enabled), i.kind, value, key=str(i.id))

    # --- events --------------------------------------------------------------

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        tid = event.control.id
        key = event.row_key.value
        if tid == "sources-table":
            current = {s.source_id: s.enabled for s in sources_store.list_sources(self._uid)}
            sources_store.set_enabled(key, not current.get(key, True), self._uid)
            self._load_sources()
        elif tid == "prefilter-table":
            cur = {r.id: r.enabled for r in disqualifiers.list_prefilter_rules(self._uid)}
            disqualifiers.set_prefilter_enabled(int(key), not cur.get(int(key), True), self._uid)
            self._load_disq()
        elif tid == "scoring-table":
            cur = {b.id: b.enabled for b in disqualifiers.list_scoring_blocks(self._uid)}
            disqualifiers.set_scoring_enabled(int(key), not cur.get(int(key), True), self._uid)
            self._load_scoring()
        elif tid == "roles-table":
            cur = {i.id: i.enabled for i in target_roles.list_target_roles(self._uid)}
            target_roles.set_enabled(int(key), not cur.get(int(key), True), self._uid)
            self._load_roles()
        event.stop()

    # --- keyboard accelerators (see BINDINGS) --------------------------------

    def _active_subtab(self) -> str:
        return self.query_one("#settings-tabs", TabbedContent).active

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool:
        """Enable an accelerator only when Settings is visible and its sub-tab
        is current; otherwise the key falls through to the focused widget."""
        subtabs = self._ACTION_SUBTABS.get(action)
        if subtabs is None:
            return True
        try:
            if self.app.query_one("#tabs", TabbedContent).active != "settings":
                return False
        except Exception:
            return False
        return self._active_subtab() in subtabs

    def action_settings_add(self) -> None:
        {
            "profile": self._add_user,
            "disq": self._add_prefilter,
            "scoring": self._add_scoring,
            "roles": self._add_role,
        }.get(self._active_subtab(), lambda: None)()

    def action_settings_delete(self) -> None:
        {
            "disq": self._del_prefilter,
            "scoring": self._del_scoring,
            "roles": self._del_role,
        }.get(self._active_subtab(), lambda: None)()

    def action_make_active(self) -> None:
        self._use_user()

    def action_toggle_active_flag(self) -> None:
        self._toggle_user()

    def action_save_config(self) -> None:
        self._save_config()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = {
            "add-user-btn": self._add_user,
            "use-user-btn": self._use_user,
            "toggle-user-btn": self._toggle_user,
            "save-config-btn": self._save_config,
            "add-prefilter-btn": self._add_prefilter,
            "del-prefilter-btn": self._del_prefilter,
            "add-scoring-btn": self._add_scoring,
            "del-scoring-btn": self._del_scoring,
            "add-role-btn": self._add_role,
            "del-role-btn": self._del_role,
        }.get(event.button.id)
        if handler:
            handler()
        event.stop()

    def _add_user(self) -> None:
        field = self.query_one("#new-user-input", Input)
        uid = field.value.strip()
        if not uid:
            return
        try:
            users.create_user(self._engine, uid)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        field.value = ""
        self.notify(f"Created user {uid}")
        self._load_users()

    def _use_user(self) -> None:
        uid = self._highlighted_user()
        if not uid:
            return
        set_active_uid(uid)
        self.notify(f"Active user is now {uid}")
        self.reload()

    def _toggle_user(self) -> None:
        uid = self._highlighted_user()
        if not uid:
            return
        u = users.get_user(self._engine, uid)
        users.set_active(self._engine, uid, not (u.active if u else True))
        self._load_users()

    def _save_config(self) -> None:
        for key in config_store.list_config(self._uid):
            try:
                inp = self.query_one(f"#cfg-{key}", Input)
            except Exception:
                continue
            config_store.set_config(key, inp.value.strip(), self._uid)
        self.notify("Config saved")

    def _add_prefilter(self) -> None:
        category = self.query_one("#prefilter-category", Select).value
        value = self.query_one("#prefilter-value", Input).value.strip()
        if not value or category is Select.BLANK:
            return
        disqualifiers.add_prefilter_rule(str(category), value, self._uid)
        self.query_one("#prefilter-value", Input).value = ""
        self._load_disq()

    def _del_prefilter(self) -> None:
        table = self.query_one("#prefilter-table", DataTable)
        if table.row_count == 0:
            return
        rid = int(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        try:
            disqualifiers.delete_prefilter_rule(rid, self._uid)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self._load_disq()

    def _add_scoring(self) -> None:
        name = self.query_one("#scoring-name", Input).value.strip()
        raw_modifier = self.query_one("#scoring-modifier", Input).value.strip()
        if not name or not raw_modifier:
            return
        try:
            modifier = int(raw_modifier)
        except ValueError:
            self.notify("Modifier must be a whole number (e.g. -20).", severity="error")
            return
        examples = [
            e.strip()
            for e in self.query_one("#scoring-examples", Input).value.split(",")
            if e.strip()
        ]
        disqualifiers.add_scoring_block(name, modifier, examples, self._uid)
        for fid in ("#scoring-name", "#scoring-modifier", "#scoring-examples"):
            self.query_one(fid, Input).value = ""
        self._load_scoring()

    def _del_scoring(self) -> None:
        table = self.query_one("#scoring-table", DataTable)
        if table.row_count == 0:
            return
        bid = int(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        try:
            disqualifiers.delete_scoring_block(bid, self._uid)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self._load_scoring()

    def _add_role(self) -> None:
        kind = self.query_one("#role-kind", Select).value
        value = self.query_one("#role-value", Input).value.strip()
        if not value or kind is Select.BLANK:
            return
        target_roles.add_target_role(str(kind), value, self._uid)
        self.query_one("#role-value", Input).value = ""
        self._load_roles()

    def _del_role(self) -> None:
        table = self.query_one("#roles-table", DataTable)
        if table.row_count == 0:
            return
        rid = int(table.coordinate_to_cell_key((table.cursor_row, 0)).row_key.value)
        try:
            target_roles.delete_target_role(rid, self._uid)
        except ValueError as e:
            self.notify(str(e), severity="error")
            return
        self._load_roles()
