"""Repo-wide nox sessions.

Per-module sessions live in each module's own ``noxfile.py``; this root file
holds checks that span the whole repository (e.g. documentation diagrams).
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import nox

nox.options.default_venv_backend = "none"

# Pinned so every contributor validates against the exact parser GitHub renders
# with. mmdc bundles the mermaid.js parser; bump deliberately.
MERMAID_IMAGE = "minlag/mermaid-cli:11.15.0"

DOCS_DIR = Path(__file__).parent / "docs"

# The image ships system chromium at CHROME_BIN but puppeteer hunts for its own
# download, so point it at the bundled binary. --no-sandbox is required because
# chromium cannot sandbox inside the container.
_PUPPETEER_CONFIG = {
    "executablePath": "/usr/bin/chromium-browser",
    "args": ["--no-sandbox", "--disable-setuid-sandbox"],
}


@nox.session(venv_backend="none", tags=["docs", "lint"])
def docs_mermaid(session):
    """Validate mermaid diagrams in docs/ via mermaid-cli in Docker.

    Covers both ```mermaid blocks inside docs/*.md and standalone docs/*.mmd
    files. mmdc parses each diagram and exits non-zero on the first syntax
    error. Runs in Docker so no Node/Chromium toolchain leaks into the Python
    venvs. Requires Docker on PATH.
    """
    if not _have_docker(session):
        session.error("docker not found on PATH — required for mermaid validation")

    sources = sorted(
        p
        for p in DOCS_DIR.glob("*.md")
        if "```mermaid" in p.read_text(encoding="utf-8")
    )
    sources += sorted(DOCS_DIR.glob("*.mmd"))
    if not sources:
        session.log("no mermaid diagrams found in docs/ — nothing to validate")
        return

    repo = DOCS_DIR.parent
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as cfg_dir:
        cfg_path = Path(cfg_dir) / "puppeteer.json"
        cfg_path.write_text(json.dumps(_PUPPETEER_CONFIG), encoding="utf-8")
        # tempfile dirs are 0700; the container's non-root user must read the mount.
        os.chmod(cfg_dir, 0o755)
        os.chmod(cfg_path, 0o644)

        for src in sources:
            rel = src.relative_to(repo).as_posix()
            session.log(f"validating {rel}")
            # .md emits a markdown copy; a bare .mmd needs an image output format.
            out = "/tmp/out.md" if src.suffix == ".md" else "/tmp/out.svg"
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{repo}:/data:ro",
                    "-v",
                    f"{cfg_dir}:/cfg:ro",
                    "-w",
                    "/data",
                    MERMAID_IMAGE,
                    "-p",
                    "/cfg/puppeteer.json",
                    "-i",
                    rel,
                    "-o",
                    out,
                    "--quiet",
                ],
                check=False,
            )
            if result.returncode != 0:
                failures.append(rel)

    if failures:
        session.error("mermaid syntax errors in: " + ", ".join(failures))
    session.log(f"all {len(sources)} mermaid diagram(s) in docs/ are valid")


def _have_docker(session) -> bool:
    try:
        subprocess.run(
            ["docker", "version"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False
