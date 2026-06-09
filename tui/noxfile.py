import nox

nox.options.default_venv_backend = "uv"


@nox.session(tags=["style", "fix"])
def ruff_format(session):
    session.install("ruff")
    session.run("ruff", "format")
    session.run("ruff", "check", "--fix")


@nox.session(tags=["test"])
def tests(session):
    # harness-db is a local path dependency, so install it editable first
    # (it is not resolvable from an index), then the TUI with its dev extras.
    session.install("-e", "../harness-db[dev]", "-e", ".[dev]")
    session.run("pytest", *session.posargs)
