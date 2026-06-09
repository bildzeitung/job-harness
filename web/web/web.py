"""Reflex app entry point for the job-harness web interface."""

from __future__ import annotations

import reflex as rx

from web.pages.companies import companies_tab
from web.pages.jobs import jobs_tab
from web.pages.settings import settings_tab
from web.settings_state import SettingsState
from web.state import AppState


def index() -> rx.Component:
    return rx.container(
        rx.vstack(
            rx.hstack(
                rx.heading("Job Harness", size="6"),
                rx.spacer(),
                rx.color_mode.button(),
                width="100%",
                align="center",
            ),
            rx.cond(
                AppState.error != "",
                rx.callout(AppState.error, color_scheme="red", icon="triangle_alert"),
            ),
            rx.tabs.root(
                rx.tabs.list(
                    rx.tabs.trigger("Jobs", value="jobs"),
                    rx.tabs.trigger("Companies", value="companies"),
                    rx.tabs.trigger("Settings", value="settings"),
                ),
                rx.tabs.content(jobs_tab(), value="jobs", padding_top="1em"),
                rx.tabs.content(companies_tab(), value="companies", padding_top="1em"),
                rx.tabs.content(settings_tab(), value="settings", padding_top="1em"),
                default_value="jobs",
                width="100%",
            ),
            spacing="4",
            width="100%",
            align="start",
        ),
        size="4",
        padding_y="1.5em",
    )


# Theme is configured via RadixThemesPlugin in rxconfig.py.
app = rx.App()
app.add_page(index, route="/", title="Job Harness", on_load=[AppState.load, SettingsState.load])
