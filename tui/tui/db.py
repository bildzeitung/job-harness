from __future__ import annotations

# Re-export the shared DB helpers (now living in harness_db) under the names the
# TUI widgets already import, so call sites stay unchanged.
from harness_db.models import Company, Posting, make_engine
from harness_db.queries import (
    get_companies,
    get_company_postings,
    get_postings,
    update_status,
)

__all__ = [
    "Company",
    "Posting",
    "make_engine",
    "get_postings",
    "get_companies",
    "get_company_postings",
    "update_status",
]
