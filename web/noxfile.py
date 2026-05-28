import nox

nox.options.default_venv_backend = "uv"


@nox.session(tags=["style", "fix"])
def ruff_format(session):
    session.install("ruff")
    session.run("ruff", "format")
    session.run("ruff", "check", "--fix")
