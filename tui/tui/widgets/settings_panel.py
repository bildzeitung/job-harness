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
            with TabPane("Target Roles", id="roles"):
                yield from self._compose_roles()

    def _compose_profile(self) -> ComposeResult:
        with Vertical():
            yield Static(id="active-user-label")
            yield DataTable(id="users-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Input(placeholder="new user id", id="new-user-input")
                yield Button("Add user", id="add-user-btn", variant="primary")
                yield Button("Make active", id="use-user-btn")
                yield Button("Toggle active flag", id="toggle-user-btn")

    def _compose_config(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Per-user config (blank inherits the env/settings fallback):")
            yield Vertical(id="config-fields")
            yield Button("Save config", id="save-config-btn", variant="primary")

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
                yield Button("Add", id="add-prefilter-btn", variant="primary")
                yield Button("Delete custom", id="del-prefilter-btn", variant="error")
            yield Static("Scoring modifiers — Enter toggles; '*' = custom.")
            yield DataTable(id="scoring-table", cursor_type="row", zebra_stripes=True)

    def _compose_roles(self) -> ComposeResult:
        with Vertical():
            yield Static("Target roles — Enter toggles; '*' = custom.")
            yield DataTable(id="roles-table", cursor_type="row", zebra_stripes=True)
            with Horizontal(classes="settings-row"):
                yield Select([(k, k) for k in KINDS], id="role-kind", prompt="kind")
                yield Input(placeholder="title / keyword / domain", id="role-value")
                yield Button("Add", id="add-role-btn", variant="primary")
                yield Button("Delete custom", id="del-role-btn", variant="error")
                yield Button("Generate target-roles.md", id="gen-roles-btn", variant="success")

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
        self._load_roles()

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
            self._load_disq()
        elif tid == "roles-table":
            cur = {i.id: i.enabled for i in target_roles.list_target_roles(self._uid)}
            target_roles.set_enabled(int(key), not cur.get(int(key), True), self._uid)
            self._load_roles()
        event.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        handler = {
            "add-user-btn": self._add_user,
            "use-user-btn": self._use_user,
            "toggle-user-btn": self._toggle_user,
            "save-config-btn": self._save_config,
            "add-prefilter-btn": self._add_prefilter,
            "del-prefilter-btn": self._del_prefilter,
            "add-role-btn": self._add_role,
            "del-role-btn": self._del_role,
            "gen-roles-btn": self._generate_roles,
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

    def _generate_roles(self) -> None:
        try:
            written = target_roles.write_target_roles_md(self._uid)
        except Exception as e:
            self.notify(f"Generate failed: {e}", severity="error")
            return
        self.notify(f"Wrote {written}")
