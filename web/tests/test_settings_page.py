"""The Settings page and its sections build into Reflex components."""

from __future__ import annotations

import reflex as rx

from web.components.settings import (
    config_section,
    disqualifiers_section,
    profile_section,
    roles_section,
    sources_section,
)
from web.pages.settings import settings_tab


def test_sections_build():
    for factory in (
        profile_section,
        config_section,
        sources_section,
        disqualifiers_section,
        roles_section,
        settings_tab,
    ):
        assert isinstance(factory(), rx.Component)
