"""Jobs data table with state-colored status badges."""

from __future__ import annotations

import reflex as rx

from web.state import AppState
from web.theme import SORT_MODES, TABLE_MAX_HEIGHT
from web.view_models import PostingVM


def _row(p: PostingVM) -> rx.Component:
    return rx.table.row(
        rx.table.row_header_cell(p.display_name),
        rx.table.cell(p.display_date),
        rx.table.cell(rx.badge(p.status, color_scheme=p.status_color)),
        on_click=lambda: AppState.select_row(p.url),
        style={"cursor": "pointer"},
        align="center",
    )


def jobs_toolbar() -> rx.Component:
    return rx.hstack(
        rx.text("Sort:", size="2"),
        rx.select(
            SORT_MODES,
            value=AppState.sort_by,
            on_change=AppState.set_sort,
            size="2",
        ),
        rx.button("Refresh", on_click=AppState.refresh, variant="soft", size="2"),
        rx.spacer(),
        rx.text(AppState.posting_count, " postings", size="2", color_scheme="gray"),
        width="100%",
        align="center",
        spacing="3",
    )


def job_table() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Job"),
                    rx.table.column_header_cell("Date"),
                    rx.table.column_header_cell("State"),
                )
            ),
            rx.table.body(rx.foreach(AppState.postings, _row)),
            variant="surface",
            size="1",
        ),
        type="auto",
        scrollbars="vertical",
        style={"maxHeight": TABLE_MAX_HEIGHT},
    )
