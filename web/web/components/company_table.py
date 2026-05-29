"""Companies data table."""

from __future__ import annotations

import reflex as rx

from web.state import AppState
from web.theme import TABLE_MAX_HEIGHT
from web.view_models import CompanyVM


def _row(c: CompanyVM) -> rx.Component:
    return rx.table.row(
        rx.table.row_header_cell(c.name),
        rx.table.cell(c.remote),
        rx.table.cell(c.canada),
        rx.table.cell(c.last_seen),
        rx.table.cell(c.notes),
        on_click=lambda: AppState.select_company(c.name),
        style={"cursor": "pointer"},
        align="center",
    )


def company_table() -> rx.Component:
    return rx.scroll_area(
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("Company"),
                    rx.table.column_header_cell("Remote"),
                    rx.table.column_header_cell("Canada"),
                    rx.table.column_header_cell("Last Seen"),
                    rx.table.column_header_cell("Notes"),
                )
            ),
            rx.table.body(rx.foreach(AppState.companies, _row)),
            variant="surface",
            size="1",
        ),
        type="auto",
        scrollbars="vertical",
        style={"maxHeight": TABLE_MAX_HEIGHT},
    )
