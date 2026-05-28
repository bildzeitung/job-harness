"""Data-driven job search across web-API sources (Adzuna, Greenhouse, Lever)."""

from api_search.core import run, write_output
from api_search.sources import SOURCES

__all__ = ["SOURCES", "run", "write_output"]
