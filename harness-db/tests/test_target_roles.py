"""Tests for harness_db.target_roles: catalog CRUD and md generation."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from harness_db import cli, target_roles
from harness_db.config import DEFAULT_UID


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HARNESS_DB", str(tmp_path / "postings.db"))
    monkeypatch.delenv("JOB_DATA_ROOT", raising=False)


def test_render_has_all_sections_and_builtins():
    md = target_roles.render_target_roles_md(DEFAULT_UID)
    assert "## Target Role Titles" in md
    assert "## Title Keywords" in md
    assert "## Domains of Interest" in md
    assert "Principal Engineer" in md  # a seeded built-in title
    assert "Cloud infrastructure" in md  # a seeded built-in domain


def test_enabled_values_by_kind():
    titles = target_roles.enabled_values("title", DEFAULT_UID)
    assert "Staff Engineer" in titles
    keywords = target_roles.enabled_values("keyword", DEFAULT_UID)
    assert "Principal" in keywords


def test_disable_drops_from_render():
    items = target_roles.list_target_roles(DEFAULT_UID)
    staff = next(i for i in items if i.kind == "title" and i.value == "Staff Engineer")
    target_roles.set_enabled(staff.id, False, DEFAULT_UID)
    md = target_roles.render_target_roles_md(DEFAULT_UID)
    # The exact bullet "- Staff Engineer" should be gone.
    assert "- Staff Engineer\n" not in md


def test_add_and_delete_custom_role():
    rid = target_roles.add_target_role("domain", "Quantum widgets", DEFAULT_UID)
    assert "Quantum widgets" in target_roles.enabled_values("domain", DEFAULT_UID)
    target_roles.delete_target_role(rid, DEFAULT_UID)
    assert "Quantum widgets" not in target_roles.enabled_values("domain", DEFAULT_UID)


def test_cannot_delete_builtin():
    builtin = next(i for i in target_roles.list_target_roles(DEFAULT_UID) if not i.custom)
    with pytest.raises(ValueError):
        target_roles.delete_target_role(builtin.id, DEFAULT_UID)


def test_write_target_roles_md_to_path(tmp_path):
    out = tmp_path / "out" / "target-roles.md"
    written = target_roles.write_target_roles_md(DEFAULT_UID, out)
    assert written == out
    assert out.read_text().startswith("# Target Job Roles")


def test_cli_show_renders_to_stdout_without_writing_a_file(tmp_path):
    """`target-roles show` prints the rendered markdown and writes no file."""
    result = CliRunner().invoke(cli.app, ["target-roles", "show", "--uid", DEFAULT_UID])
    assert result.exit_code == 0
    assert "# Target Job Roles" in result.stdout
    assert "Principal Engineer" in result.stdout  # a seeded built-in title
    assert not (tmp_path / "target-roles.md").exists()
