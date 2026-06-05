"""Tests for harness_db.embeddings (Ollama mocked — no GPU/daemon needed)."""

from __future__ import annotations

import sys
import types

import pytest

from harness_db import embeddings


def _fake_ollama(monkeypatch, capture: dict, dim: int | None = None):
    dim = embeddings.EMBED_DIM if dim is None else dim

    def fake_embeddings(model, prompt, options):
        capture["model"] = model
        capture["prompt"] = prompt
        capture["options"] = options
        return {"embedding": [0.0] * dim}

    module = types.ModuleType("ollama")
    module.embeddings = fake_embeddings
    monkeypatch.setitem(sys.modules, "ollama", module)


def test_embed_passes_num_ctx_and_truncates(monkeypatch):
    capture: dict = {}
    _fake_ollama(monkeypatch, capture)

    out = embeddings.embed("x" * 20000)

    assert isinstance(out, bytes)
    assert len(out) == embeddings.EMBED_DIM * 4  # float32
    # Raised context window is what stops Ollama 500-ing on long JDs.
    assert capture["options"] == {"num_ctx": embeddings.EMBED_NUM_CTX}
    # Instruction wrapper + text truncated to _MAX_CHARS.
    assert capture["prompt"] == embeddings._INSTRUCTION + "x" * embeddings._MAX_CHARS


def test_embed_raises_on_dim_mismatch(monkeypatch):
    capture: dict = {}
    _fake_ollama(monkeypatch, capture, dim=7)

    with pytest.raises(ValueError, match="expected"):
        embeddings.embed("hello")
