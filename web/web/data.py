"""Thin data layer: resolve the engine once and return view models to the state."""

from __future__ import annotations

from functools import lru_cache

from harness_db.config import get_db_path
from harness_db.models import Engine, make_engine
from harness_db.queries import get_companies, get_postings, update_status

from web.view_models import CompanyVM, PostingVM


@lru_cache(maxsize=1)
def engine() -> Engine:
    return make_engine(get_db_path())


def load_postings(sort_by: str) -> list[PostingVM]:
    return [PostingVM.from_orm(p) for p in get_postings(engine(), sort_by)]


def load_companies() -> list[CompanyVM]:
    return [CompanyVM.from_orm(c) for c in get_companies(engine())]


def set_status(url: str, status: str) -> None:
    update_status(engine(), url, status)
