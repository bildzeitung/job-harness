# Matchwright logo

A cheerful cartoon goose cradling a steaming mug of coffee — plain lines and
flat colour, drawn as a circular patch (so it works as a patch or app icon) with
a curved `MATCHWRIGHT` wordmark, happy eyes, a shaped bill, a grin, and a couple
of sparkles. The goose is a mascot; it does not literally depict the name.

| File | Use |
| --- | --- |
| `logo.svg` | Canonical web/vector version (256×256, circular). Served by the web app from `web/assets/logo.svg`. |
| `logo.txt` | Text logo — goose with a coffee mug, drawn with Unicode box-drawing/blocks (not 7-bit ASCII). Mirrored in `tui/tui/logo.py` as `GOOSE_LOGO`. |

## Palette

| Role | Colour |
| --- | --- |
| Sky badge | `#BFE6F2` |
| Goose body | `#FFFFFF` |
| Beak / feet | `#F6A623` |
| Mug | `#E2654F` |
| Coffee | `#5A3A22` |
| Sparkles | `#FFD24A` |
| Outline / eye / wordmark | `#2B2B2B` |

When updating the design, change `logo.svg` here first (the source of truth) and
copy it to `web/assets/logo.svg`; keep `logo.txt` and `tui/tui/logo.py` in sync.
