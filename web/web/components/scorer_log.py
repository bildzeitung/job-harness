"""Live agent-output log panel (streams stream-json events)."""

from __future__ import annotations

import reflex as rx

from web.state import AppState
from web.theme import SCORER_LOG_MAX_HEIGHT


def _line(text: str) -> rx.Component:
    return rx.text(text, style={"whiteSpace": "pre-wrap", "fontFamily": "monospace"}, size="1")


def scorer_log() -> rx.Component:
    return rx.cond(
        AppState.scorer_open,
        rx.card(
            rx.vstack(
                rx.hstack(
                    rx.heading("Agent output", size="4"),
                    rx.cond(AppState.scorer_running, rx.spinner(size="2")),
                    rx.spacer(),
                    rx.button("Hide", on_click=AppState.toggle_scorer, variant="ghost", size="1"),
                    width="100%",
                    align="center",
                ),
                rx.divider(),
                rx.scroll_area(
                    rx.vstack(
                        rx.foreach(AppState.scorer_lines, _line),
                        spacing="0",
                        align="start",
                    ),
                    type="auto",
                    scrollbars="vertical",
                    style={"maxHeight": SCORER_LOG_MAX_HEIGHT},
                ),
                spacing="2",
                width="100%",
                align="start",
            ),
            width="100%",
        ),
    )
