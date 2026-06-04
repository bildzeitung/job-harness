"""Vector helper tests.

Exercises the KNN / duplicate logic against a real sqlite-vec table but with
``vectors.embed`` monkeypatched to deterministic vectors, so no Ollama or GPU is
needed. sqlite-vec is a required dependency, so there is nothing to skip.
"""

from __future__ import annotations

import array

import pytest

from harness_db import vectors
from harness_db.embeddings import EMBED_DIM
from harness_db.models import make_engine


def _vec(*nonzero: tuple[int, float]) -> bytes:
    """Build EMBED_DIM float32 bytes with the given (index, value) entries set."""
    buf = [0.0] * EMBED_DIM
    for i, v in nonzero:
        buf[i] = v
    return array.array("f", buf).tobytes()


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    eng = make_engine(tmp_path / "postings.db")
    # Map the text passed to upsert/nearest onto a fixed vector. 'a' and 'b' are
    # near-identical (tiny perturbation); 'c' is orthogonal to both.
    fakes = {
        "a": _vec((0, 1.0)),
        "b": _vec((0, 0.999), (1, 0.001)),
        "c": _vec((500, 1.0)),
    }
    monkeypatch.setattr(vectors, "embed", lambda text: fakes[text])
    return eng


def test_nearest_orders_by_distance(engine):
    vectors.upsert_vector(engine, "u-a", "a")
    vectors.upsert_vector(engine, "u-b", "b")
    vectors.upsert_vector(engine, "u-c", "c")

    hits = vectors.nearest(engine, "a", k=2, exclude_url="u-a")
    assert [url for url, _ in hits] == ["u-b", "u-c"]
    assert hits[0][1] < hits[1][1]  # b closer than c


def test_find_duplicate_hits_and_misses(engine):
    vectors.upsert_vector(engine, "u-a", "a")
    vectors.upsert_vector(engine, "u-c", "c")

    # 'b' is ~identical to the stored 'a' -> duplicate.
    dup = vectors.find_duplicate(engine, "b")
    assert dup is not None and dup[0] == "u-a"
    assert dup[1] <= vectors.DUPLICATE_DISTANCE

    # 'c' against everything-but-itself is orthogonal -> no duplicate.
    assert vectors.find_duplicate(engine, "c", exclude_url="u-c") is None


def test_missing_extension_support_raises_clear_error():
    """The semantic layer is mandatory: an extension-less sqlite3 must fail loudly."""
    from harness_db import models

    class _FakeConn:  # deliberately lacks enable_load_extension
        def execute(self, *args):
            raise AssertionError("should not reach CREATE without extension support")

    with pytest.raises(RuntimeError, match="loadable-extension"):
        models._load_sqlite_vec(_FakeConn())


def test_upsert_replaces_and_delete_removes(engine):
    vectors.upsert_vector(engine, "u-a", "a")
    vectors.upsert_vector(engine, "u-a", "c")  # replace same url with a new vector
    assert vectors.find_duplicate(engine, "a", exclude_url=None) is None  # 'a' gone
    assert vectors.find_duplicate(engine, "c") is not None

    vectors.delete_vector(engine, "u-a")
    assert vectors.nearest(engine, "c") == []
