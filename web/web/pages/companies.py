"""Companies tab: table and detail panel."""

from __future__ import annotations

import reflex as rx

from web.components.company_detail import company_detail
from web.components.company_table import company_table
from web.state import AppState


def companies_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.spacer(),
            rx.text(AppState.company_count, " companies", size="2", color_scheme="gray"),
            width="100%",
        ),
        company_table(),
        company_detail(),
        spacing="4",
        width="100%",
        align="start",
    )
