"""Tests for harness_db.backfill_embeddings (upsert mocked — no Ollama)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from harness_db import backfill_embeddings as bf
from harness_db.models import Base, Posting, make_engine


def _seed(tmp_path):
    db = tmp_path / "postings.db"
    engine = make_engine(db)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Posting(url="u1", title="Role A", status="new"))
        s.add(Posting(url="u2", title="Role B", status="new"))
        s.commit()
    return db


def test_backfill_full_embeds_all(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    embedded: list[str] = []
    monkeypatch.setattr(bf, "upsert_vector", lambda engine, url, text: embedded.append(url))
    monkeypatch.setattr(bf, "get_db_path", lambda: db)

    assert bf.run(missing_only=False) == 0
    assert set(embedded) == {"u1", "u2"}


def test_backfill_missing_only_skips_indexed(tmp_path, monkeypatch):
    db = _seed(tmp_path)
    embedded: list[str] = []
    monkeypatch.setattr(bf, "upsert_vector", lambda engine, url, text: embedded.append(url))
    monkeypatch.setattr(bf, "_indexed_urls", lambda engine: {"u1"})
    monkeypatch.setattr(bf, "get_db_path", lambda: db)

    assert bf.run(missing_only=True) == 0
    assert embedded == ["u2"]  # u1 already indexed → skipped


def test_backfill_skips_textless_posting(tmp_path, monkeypatch):
    db = tmp_path / "postings.db"
    engine = make_engine(db)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Posting(url="u1", status="new"))  # no title/summary/JD
        s.commit()
    embedded: list[str] = []
    monkeypatch.setattr(bf, "upsert_vector", lambda engine, url, text: embedded.append(url))
    monkeypatch.setattr(bf, "get_db_path", lambda: db)

    assert bf.run() == 0
    assert embedded == []


def test_backfill_cli_passes_missing_only(monkeypatch):
    """The Typer CLI wires --missing-only through to run()."""
    from typer.testing import CliRunner

    seen: dict = {}

    def fake_run(missing_only=False):
        seen["missing_only"] = missing_only
        return 0

    monkeypatch.setattr(bf, "run", fake_run)

    assert CliRunner().invoke(bf.app, ["--missing-only"]).exit_code == 0
    assert seen["missing_only"] is True

    assert CliRunner().invoke(bf.app, []).exit_code == 0
    assert seen["missing_only"] is False
