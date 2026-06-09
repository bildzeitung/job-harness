"""Tests for the new harness-db CLI groups: user, config, sources, disqualifiers, target-roles."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from harness_db import cli, config_store, disqualifiers, sources_store

runner = CliRunner()


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "postings.db"))
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)
    for c in (config_store._engine_for, disqualifiers._engine_for, sources_store._engine):
        c.cache_clear()


def test_user_add_list_use_show():
    assert runner.invoke(cli.app, ["user", "add", "alice", "--use"]).exit_code == 0
    show = runner.invoke(cli.app, ["user", "show"])
    assert show.stdout.strip() == "alice"
    listing = runner.invoke(cli.app, ["user", "list"])
    assert "* alice" in listing.stdout


def test_user_add_duplicate_fails():
    runner.invoke(cli.app, ["user", "add", "bob"])
    res = runner.invoke(cli.app, ["user", "add", "bob"])
    assert res.exit_code == 1


def test_config_set_get_list():
    assert runner.invoke(cli.app, ["config", "set", "RESUME_FILE", "/x.yaml"]).exit_code == 0
    got = runner.invoke(cli.app, ["config", "get", "RESUME_FILE"])
    assert got.stdout.strip() == "/x.yaml"
    listing = runner.invoke(cli.app, ["config", "list"])
    assert "RESUME_FILE" in listing.stdout


def test_sources_disable_reflected_in_enabled_json():
    runner.invoke(cli.app, ["sources", "disable", "linkedin"])
    res = runner.invoke(cli.app, ["sources", "enabled"])
    payload = json.loads(res.stdout)
    assert "linkedin" not in payload["enabled"]


def test_disqualifiers_add_and_list():
    add = runner.invoke(cli.app, ["disqualifiers", "add", "title_terms", "widgetcli"])
    assert add.exit_code == 0
    listing = runner.invoke(cli.app, ["disqualifiers", "list"])
    assert "widgetcli" in listing.stdout


def test_target_roles_add_and_generate(tmp_path):
    runner.invoke(cli.app, ["target-roles", "add", "title", "Galaxy Engineer"])
    out = tmp_path / "tr.md"
    res = runner.invoke(cli.app, ["target-roles", "generate", "--path", str(out)])
    assert res.exit_code == 0
    assert "Galaxy Engineer" in out.read_text()
