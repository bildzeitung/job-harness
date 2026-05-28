"""Detail panel for the selected company."""

from __future__ import annotations

import reflex as rx

from web.state import AppState


def company_detail() -> rx.Component:
    return rx.cond(
        AppState.company_detail_open,
        rx.card(
            rx.vstack(
                rx.heading(AppState.company_name, size="4"),
                rx.divider(),
                rx.text(
                    AppState.company_detail,
                    style={"whiteSpace": "pre-wrap", "fontFamily": "monospace"},
                    size="2",
                ),
                spacing="3",
                align="start",
                width="100%",
            ),
            width="100%",
        ),
    )
