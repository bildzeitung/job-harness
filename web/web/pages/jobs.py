"""Jobs tab: toolbar, table, detail panel, and agent-output log."""

from __future__ import annotations

import reflex as rx

from web.components.job_detail import job_detail
from web.components.job_table import job_table, jobs_toolbar
from web.components.scorer_log import scorer_log


def jobs_tab() -> rx.Component:
    return rx.vstack(
        jobs_toolbar(),
        job_table(),
        job_detail(),
        scorer_log(),
        spacing="4",
        width="100%",
        align="start",
    )
