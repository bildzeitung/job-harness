from __future__ import annotations

# DB-path discovery now lives in harness_db so every front-end resolves it the same way.
from harness_db.config import get_db_path

__all__ = ["get_db_path"]
