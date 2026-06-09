import nox

nox.options.default_venv_backend = "uv"


@nox.session(tags=["style", "fix"])
def ruff_format(session):
    session.install("ruff")
    session.run("ruff", "format")
    session.run("ruff", "check", "--fix")


@nox.session(tags=["test"])
def tests(session):
    session.install("-e", ".[dev]")
    session.run("pytest", *session.posargs)
