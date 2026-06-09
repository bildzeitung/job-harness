#!/bin/bash -ex

# --- Pre-flight --------------------------------------------------------------
# The semantic dedup/similarity layer (sqlite-vec) is a mandatory part of the
# harness, so the Python that builds the venv must have a sqlite3 capable of
# loading extensions. Check up front and stop with guidance, rather than failing
# deep inside a database call later. Run quietly so the message stands out.
set +x
if ! python -c 'import sqlite3, sys; sys.exit(0 if hasattr(sqlite3.connect(":memory:"), "enable_load_extension") else 1)'; then
    echo "ERROR: this Python's sqlite3 was built without loadable-extension support," >&2
    echo "       which the harness requires. Rebuild Python with:" >&2
    echo '         PYTHON_CONFIGURE_OPTS="${PYTHON_CONFIGURE_OPTS} --enable-loadable-sqlite-extensions" \' >&2
    echo "           pyenv install --force 3.14.5" >&2
    exit 1
fi

# Ollama serving the embedding model powers that layer; 3rdparty-install.sh
# installs Ollama and pulls the model. Warn (don't fail) so setup can proceed if
# you run that script afterwards.
EMBED_MODEL="qwen3-embedding:0.6b"  # keep in sync with harness_db.embeddings.EMBED_MODEL
if command -v ollama >/dev/null 2>&1; then
    ollama list 2>/dev/null | grep -qF "$EMBED_MODEL" \
        || echo "WARNING: Ollama model '$EMBED_MODEL' not found — run ./3rdparty-install.sh" >&2
else
    echo "WARNING: 'ollama' not on PATH — run ./3rdparty-install.sh to install it and pull $EMBED_MODEL." >&2
fi
set -x

./scripts/python-init.sh

