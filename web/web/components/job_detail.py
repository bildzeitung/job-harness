"""Detail panel for the selected posting, with status/agent action buttons."""

from __future__ import annotations

import reflex as rx

from web.state import AppState


def _actions() -> rx.Component:
    return rx.hstack(
        rx.cond(
            AppState.can_score,
            rx.button("Score new", on_click=AppState.score_new, color_scheme="cyan", size="2"),
        ),
        rx.cond(
            AppState.can_prepare,
            rx.button("Prepare", on_click=AppState.prepare, color_scheme="purple", size="2"),
        ),
        rx.cond(
            AppState.can_apply,
            rx.button(
                "Mark applied",
                on_click=AppState.mark_applied,
                color_scheme="tomato",
                variant="soft",
                size="2",
            ),
        ),
        rx.cond(
            AppState.can_reject,
            rx.button(
                "Mark rejected",
                on_click=AppState.mark_rejected,
                color_scheme="red",
                variant="soft",
                size="2",
            ),
        ),
        spacing="2",
        wrap="wrap",
    )


def job_detail() -> rx.Component:
    return rx.cond(
        AppState.detail_open,
        rx.card(
            rx.vstack(
                rx.heading(AppState.selected_name, size="4"),
                _actions(),
                rx.divider(),
                rx.text(
                    AppState.selected_detail,
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
