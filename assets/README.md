# Job Harness logo

The head of a cheerful goose, facing right — plain lines and flat colour, drawn
as a circular patch (so it works as a patch or app icon) with a curved
`JOB HARNESS` wordmark, a smiling bill, a happy eye, and a couple of sparkles.

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
