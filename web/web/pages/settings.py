"""Settings tab: profile, config, sources, disqualifiers, target roles."""

from __future__ import annotations

import reflex as rx

from web.components.settings import (
    config_section,
    disqualifiers_section,
    profile_section,
    roles_section,
    sources_section,
)
from web.settings_state import SettingsState


def settings_tab() -> rx.Component:
    return rx.vstack(
        rx.cond(
            SettingsState.message != "",
            rx.callout(SettingsState.message, color_scheme="green", icon="info"),
        ),
        profile_section(),
        config_section(),
        sources_section(),
        disqualifiers_section(),
        roles_section(),
        spacing="4",
        width="100%",
        align="start",
    )
