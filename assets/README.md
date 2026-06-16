# Matchwright logo

A cheerful cartoon goose — plain lines and flat colour, drawn as a circular
patch (so it works as a patch or app icon) with a curved `MATCHWRIGHT` wordmark,
happy eyes, a grin, and a couple of sparkles. The goose is a mascot; it does not
literally depict the name.

| File | Use |
| --- | --- |
| `logo.svg` | Canonical web/vector version (256×256, circular). Served by the web app from `web/assets/logo.svg`. |
| `logo.txt` | ASCII version. Embedded in the TUI banner (`tui/tui/logo.py`). |

## Palette

| Role | Colour |
| --- | --- |
| Sky badge | `#BFE6F2` |
| Goose body | `#FFFFFF` |
| Beak | `#F6A623` |
| Sparkles | `#FFD24A` |
| Outline / eye / wordmark | `#2B2B2B` |

When updating the design, change `logo.svg` here first (the source of truth) and
copy it to `web/assets/logo.svg`; keep `logo.txt` and `tui/tui/logo.py` in sync.
