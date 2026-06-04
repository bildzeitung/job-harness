"""Local text embeddings via Ollama for semantic dedup and similarity.

Vectors are produced by a local Ollama model (default ``qwen3-embedding:0.6b``,
1024-dim) and stored in the ``postings_vec`` sqlite-vec table that lives inside
the same ``postings.db``. Both sides of every comparison are embedded with the
*identical* instruction wrapper so distances stay symmetric — required for
near-duplicate detection, where the "query" and the "document" are both job
postings.

``ollama`` and ``numpy`` are imported lazily inside ``embed`` so that merely
importing this module (e.g. for the EMBED_DIM constant in models.py) doesn't pull
the embedding stack until an embedding is actually requested.
"""

from __future__ import annotations

import os

# qwen3-embedding:0.6b emits 1024-dim vectors and fits the GTX 1080 Ti with room
# to spare. If you switch EMBED_MODEL to a different width (e.g. nomic-embed-text
# -> 768) you MUST update EMBED_DIM, recreate the postings_vec table at the new
# width, and re-embed the whole corpus: vectors from different models are not
# comparable.
EMBED_MODEL = os.environ.get("HARNESS_EMBED_MODEL", "qwen3-embedding:0.6b")
EMBED_DIM = int(os.environ.get("HARNESS_EMBED_DIM", "1024"))

# Max chars fed to the embedder. Mirrors the scorer's JD truncation so dedup
# compares the same text the scorer reasons over (scoring_module JD_TRUNCATE_LENGTH).
_MAX_CHARS = 8000

# One instruction applied to BOTH stored documents and lookup text. Keeping it
# identical on both sides is what makes the cosine metric symmetric for dedup
# (Qwen3-Embedding is instruction-tuned; an asymmetric query/document split is
# for retrieval, not for "are these the same posting?").
_INSTRUCTION = (
    "Instruct: Represent this job posting for duplicate detection and similarity search.\nText: "
)


def _format(text: str) -> str:
    return _INSTRUCTION + (text or "")[:_MAX_CHARS]


def embed(text: str) -> bytes:
    """Embed ``text`` and return raw float32 bytes for sqlite-vec storage/query."""
    import numpy as np
    import ollama

    resp = ollama.embeddings(model=EMBED_MODEL, prompt=_format(text))
    vec = np.asarray(resp["embedding"], dtype=np.float32)
    if vec.shape != (EMBED_DIM,):
        raise ValueError(
            f"{EMBED_MODEL} returned {vec.shape[0]} dims, expected {EMBED_DIM}. "
            "Set HARNESS_EMBED_DIM and the postings_vec table width to match."
        )
    return vec.tobytes()
