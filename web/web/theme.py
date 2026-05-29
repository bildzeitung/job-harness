"""Display constants for the web UI (colors, sort modes, layout sizes)."""

from __future__ import annotations

# Maps a posting status to a Radix color scheme for its badge.
# Mirrors the TUI's STATE_STYLES intent (tui/tui/widgets/jobs_panel.py).
STATE_COLORS: dict[str, str] = {
    "new": "green",
    "scored": "cyan",
    "selected": "amber",
    "prepared": "purple",
    "applied": "tomato",
    "rejected": "red",
    "skipped": "gray",
}

# Badge color for any status not present in STATE_COLORS.
DEFAULT_STATE_COLOR = "gray"

# Sort modes offered in the UI, matching harness_db.queries ordering.
SORT_MODES = ["state", "date", "title"]
DEFAULT_SORT = "state"

# Glyphs for tri-state booleans in the companies table.
GLYPH_TRUE = "✓"
GLYPH_FALSE = "✗"
GLYPH_UNKNOWN = "—"

# Max height (viewport units) for the scrollable agent-output log.
SCORER_LOG_MAX_HEIGHT = "40vh"
# Max height (viewport units) for the data tables.
TABLE_MAX_HEIGHT = "70vh"


def state_color(status: str | None) -> str:
    return STATE_COLORS.get(status or "new", DEFAULT_STATE_COLOR)
