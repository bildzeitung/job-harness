"""Settings UI: profile, config, sources, disqualifiers, target roles."""

from __future__ import annotations

import reflex as rx

from web.settings_state import (
    ConfigRowVM,
    RuleRowVM,
    SettingsState,
    SourceRowVM,
    UserRowVM,
)


def _heading(text: str) -> rx.Component:
    return rx.heading(text, size="4", margin_top="1em")


# --- profile -----------------------------------------------------------------


def _user_row(u: UserRowVM) -> rx.Component:
    return rx.table.row(
        rx.table.cell(rx.cond(u.is_current, "→", "")),
        rx.table.row_header_cell(u.uid),
        rx.table.cell(
            rx.cond(u.active, rx.badge("active"), rx.badge("inactive", color_scheme="gray"))
        ),
        rx.table.cell(
            rx.hstack(
                rx.button(
                    "Make active",
                    size="1",
                    variant="soft",
                    on_click=lambda: SettingsState.use_user(u.uid),
                ),
                rx.button(
                    "Toggle flag",
                    size="1",
                    variant="soft",
                    on_click=lambda: SettingsState.toggle_user_active(u.uid),
                ),
                spacing="2",
            )
        ),
        align="center",
    )


def profile_section() -> rx.Component:
    return rx.vstack(
        _heading("Profile"),
        rx.text("Active user: ", rx.text.strong(SettingsState.active_uid), size="2"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell(""),
                    rx.table.column_header_cell("User"),
                    rx.table.column_header_cell("Flag"),
                    rx.table.column_header_cell(""),
                )
            ),
            rx.table.body(rx.foreach(SettingsState.users, _user_row)),
            variant="surface",
            size="1",
        ),
        rx.hstack(
            rx.input(
                placeholder="new user id",
                value=SettingsState.new_user,
                on_change=SettingsState.set_new_user,
                size="2",
            ),
            rx.button("Create account", on_click=SettingsState.add_user, size="2"),
            spacing="2",
        ),
        spacing="2",
        width="100%",
        align="start",
    )


# --- config ------------------------------------------------------------------


def _config_row(c: ConfigRowVM) -> rx.Component:
    return rx.hstack(
        rx.text(c.key, width="12em", size="2"),
        rx.input(
            default_value=c.value,
            placeholder="(inherits env / settings fallback)",
            on_blur=lambda v: SettingsState.set_config_edit(c.key, v),
            width="100%",
            size="2",
        ),
        width="100%",
        align="center",
        spacing="2",
    )


def config_section() -> rx.Component:
    return rx.vstack(
        _heading("Config"),
        rx.foreach(SettingsState.configs, _config_row),
        rx.button("Save config", on_click=SettingsState.save_config, size="2"),
        spacing="2",
        width="100%",
        align="start",
    )


# --- sources -----------------------------------------------------------------


def _source_row(s: SourceRowVM) -> rx.Component:
    return rx.hstack(
        rx.switch(checked=s.enabled, on_change=lambda v: SettingsState.set_source(s.source_id, v)),
        rx.text(s.source_id, width="9em", size="2", weight="bold"),
        rx.text(s.description, size="2", color_scheme="gray"),
        width="100%",
        align="center",
        spacing="3",
    )


def sources_section() -> rx.Component:
    return rx.vstack(
        _heading("Sources"),
        rx.foreach(SettingsState.sources, _source_row),
        spacing="2",
        width="100%",
        align="start",
    )


# --- disqualifiers -----------------------------------------------------------


def _prefilter_row(r: RuleRowVM) -> rx.Component:
    return rx.hstack(
        rx.switch(checked=r.enabled, on_change=lambda v: SettingsState.set_prefilter(r.id, v)),
        rx.badge(r.sublabel, color_scheme="gray"),
        rx.text(r.label, size="2"),
        rx.cond(r.custom, rx.badge("custom")),
        rx.spacer(),
        rx.cond(
            r.custom,
            rx.button(
                "Delete",
                size="1",
                variant="soft",
                color_scheme="red",
                on_click=lambda: SettingsState.delete_prefilter(r.id),
            ),
        ),
        width="100%",
        align="center",
        spacing="3",
    )


def _scoring_row(b: RuleRowVM) -> rx.Component:
    return rx.hstack(
        rx.switch(checked=b.enabled, on_change=lambda v: SettingsState.set_scoring(b.id, v)),
        rx.badge(b.sublabel, color_scheme="gray"),
        rx.text(b.label, size="2"),
        rx.cond(b.custom, rx.badge("custom")),
        width="100%",
        align="center",
        spacing="3",
    )


def disqualifiers_section() -> rx.Component:
    return rx.vstack(
        _heading("Disqualifiers"),
        rx.text("Prefilter rules", weight="bold", size="2"),
        rx.foreach(SettingsState.prefilters, _prefilter_row),
        rx.hstack(
            rx.select(
                SettingsState.prefilter_categories,
                value=SettingsState.new_prefilter_category,
                on_change=SettingsState.set_new_prefilter_category,
                size="2",
            ),
            rx.input(
                placeholder="keyword / phrase",
                value=SettingsState.new_prefilter_value,
                on_change=SettingsState.set_new_prefilter_value,
                size="2",
            ),
            rx.button("Add", on_click=SettingsState.add_prefilter, size="2"),
            spacing="2",
        ),
        rx.text("Scoring modifier blocks", weight="bold", size="2", margin_top="0.5em"),
        rx.foreach(SettingsState.scorings, _scoring_row),
        spacing="2",
        width="100%",
        align="start",
    )


# --- target roles ------------------------------------------------------------


def _role_row(i: RuleRowVM) -> rx.Component:
    return rx.hstack(
        rx.switch(checked=i.enabled, on_change=lambda v: SettingsState.set_role(i.id, v)),
        rx.badge(i.sublabel, color_scheme="gray"),
        rx.text(i.label, size="2"),
        rx.cond(i.custom, rx.badge("custom")),
        rx.spacer(),
        rx.cond(
            i.custom,
            rx.button(
                "Delete",
                size="1",
                variant="soft",
                color_scheme="red",
                on_click=lambda: SettingsState.delete_role(i.id),
            ),
        ),
        width="100%",
        align="center",
        spacing="3",
    )


def roles_section() -> rx.Component:
    return rx.vstack(
        _heading("Target Roles"),
        rx.foreach(SettingsState.roles, _role_row),
        rx.hstack(
            rx.select(
                SettingsState.role_kinds,
                value=SettingsState.new_role_kind,
                on_change=SettingsState.set_new_role_kind,
                size="2",
            ),
            rx.input(
                placeholder="title / keyword / domain",
                value=SettingsState.new_role_value,
                on_change=SettingsState.set_new_role_value,
                size="2",
            ),
            rx.button("Add", on_click=SettingsState.add_role, size="2"),
            spacing="2",
        ),
        spacing="2",
        width="100%",
        align="start",
    )
