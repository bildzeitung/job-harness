"""ASCII goose logo for the Matchwright TUI.

The full square logo lives in ``assets/logo.txt`` at the repo root; this module
holds a compact banner variant sized for the app header. Keep the two in sync.
"""

from __future__ import annotations

# Compact, header-sized cheerful goose, with wordmark.
GOOSE_BANNER = r"""   .-""-.
  ( ^ ^ )   Matchwright
   \__/      honk!"""

# Full cartoon goose (mirrors assets/logo.txt).
GOOSE_LOGO = r"""            ~
          .-""-.
     *    / ^  ^ \    *
         |   <>   |
          \ \__/ /
        ___|    |___
       /            \
      |    (    )    |
      |              |
       \            /
        '._      _.'
           '----'
          _/      \_
        (__)      (__)

       M A T C H W R I G H T"""
