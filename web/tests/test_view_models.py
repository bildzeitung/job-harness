"""Tests for ORM -> view-model conversion."""

from __future__ import annotations

from harness_db.models import Company, Posting

from web.view_models import CompanyVM, PostingVM


def test_posting_vm_basic_fields_and_color():
    p = Posting(
        url="https://x/1",
        title="Engineer",
        company="Acme",
        first_seen="2026-05-01T10:00:00",
        status="new",
    )
    vm = PostingVM.from_orm(p)
    assert vm.url == "https://x/1"
    assert vm.title == "Engineer"
    assert vm.company == "Acme"
    assert vm.display_name == "Acme · Engineer"
    assert vm.display_date == "2026/05/01"
    assert vm.status == "new"
    assert vm.status_color == "green"
    assert "URL: https://x/1" in vm.detail_text


def test_posting_vm_status_defaults_to_new():
    p = Posting(url="https://x/2", title="T", company="C", status=None)
    vm = PostingVM.from_orm(p)
    assert vm.status == "new"


def test_posting_vm_detail_includes_score_when_present():
    p = Posting(
        url="https://x/3",
        title="T",
        company="C",
        status="scored",
        final_score=87,
        base_score=80,
        modifier=7,
    )
    vm = PostingVM.from_orm(p)
    assert "Score:    87  (base 80, modifier +7)" in vm.detail_text
    assert vm.status_color == "cyan"


def test_company_vm_glyphs_and_detail():
    c = Company(
        name="Acme",
        remote_confirmed=True,
        canada_confirmed=False,
        last_seen_date="2026-05-20T00:00:00",
        notes="Great place",
    )
    vm = CompanyVM.from_orm(c)
    assert vm.name == "Acme"
    assert vm.remote == "✓"
    assert vm.canada == "✗"
    assert vm.last_seen == "2026-05-20"
    assert vm.notes == "Great place"
    assert "Company:  Acme" in vm.detail_text


def test_company_vm_unknown_booleans():
    c = Company(name="Beta", remote_confirmed=None, canada_confirmed=None)
    vm = CompanyVM.from_orm(c)
    assert vm.remote == "—"
    assert vm.canada == "—"
