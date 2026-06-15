"""ASCII goose logo for the Job Harness TUI.

The full square logo lives in ``assets/logo.txt`` at the repo root; this module
holds a compact banner variant sized for the app header. Keep the two in sync.
"""

from __future__ import annotations

# Compact, header-sized goose head facing right, with wordmark.
GOOSE_BANNER = r"""   __
  (o )___      Job Harness
   \____ >"""

# Full square goose head (mirrors assets/logo.txt).
GOOSE_LOGO = r"""       __
      /  \
     | o   \___
     |        __ >
      \      /
       |    |
       |    |
      _|    |_
     /        \

      JOB HARNESS"""
