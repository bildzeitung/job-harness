import nox

nox.options.default_venv_backend = "uv"


@nox.session(tags=["style", "fix"])
def ruff_format(session):
    session.install("ruff")
    session.run("ruff", "format")
    session.run("ruff", "check", "--fix")


@nox.session(tags=["test"])
def tests(session):
    # consolidate-module is installed editable so the companies-policy sync-guard
    # test can import consolidate_module.consolidator.PLATFORMS (its only use).
    session.install("-e", ".[dev]", "-e", "../consolidate-module")
    session.run("pytest", *session.posargs)
