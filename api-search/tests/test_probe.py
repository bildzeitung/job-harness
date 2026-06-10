"""Tests for api_search.probe — ATS board slug health probing."""

import httpx
import pytest

from api_search.__main__ import main
from api_search.probe import EMPTY, ERROR, GONE, OK, PROBES, ProbeResult, probe_slugs
from tests.conftest import FakeResp, make_client

CONFIG = {
    "greenhouse": {"slugs": ["acme"]},
    "lever": {"slugs": ["deadco"]},
    "ashby": {"slugs": ["emptyco"]},
    "workable": {"slugs": ["flakyco"]},
    "recruitee": {"slugs": ["hireco"]},
}


@pytest.fixture
def config(monkeypatch):
    monkeypatch.setattr("api_search.probe.load_config", lambda: CONFIG)


def _route(url, params):
    if "greenhouse" in url:
        return FakeResp({"jobs": [{"id": 1}, {"id": 2}]})
    if "lever" in url:
        return FakeResp({}, status=404)
    if "ashby" in url:
        return FakeResp({"jobs": []})
    if "workable" in url:
        return FakeResp({}, status=500)
    return FakeResp({"offers": [{"id": 1}]})


def test_probe_slugs_buckets_each_status(config):
    results = probe_slugs(client=make_client(_route))
    by_source = {r.source: r for r in results}

    assert by_source["greenhouse"] == ProbeResult("greenhouse", "acme", OK, "2 jobs")
    assert by_source["lever"] == ProbeResult("lever", "deadco", GONE, "HTTP 404")
    assert by_source["ashby"] == ProbeResult("ashby", "emptyco", EMPTY, "0 jobs")
    assert by_source["workable"] == ProbeResult("workable", "flakyco", ERROR, "HTTP 500")
    assert by_source["recruitee"] == ProbeResult("recruitee", "hireco", OK, "1 jobs")


def test_probe_slugs_network_error_is_error_not_crash(config):
    def route(url, params):
        raise httpx.ConnectError("boom")

    results = probe_slugs(["greenhouse"], client=make_client(route))
    assert results == [ProbeResult("greenhouse", "acme", ERROR, "boom")]


def test_probe_slugs_filters_to_requested_sources(config):
    results = probe_slugs(["greenhouse", "recruitee"], client=make_client(_route))
    assert [r.source for r in results] == ["greenhouse", "recruitee"]


def test_probe_slugs_rejects_non_slug_source(config):
    with pytest.raises(ValueError, match="adzuna"):
        probe_slugs(["adzuna"], client=make_client(_route))


def test_probe_covers_every_slug_source():
    # Sync guard: every slug-based source in the packaged config has a probe.
    from api_search.sources import load_config

    slug_sources = {name for name, cfg in load_config().items() if "slugs" in cfg}
    assert slug_sources == set(PROBES)


def test_main_probe_slugs_exit_codes(monkeypatch, capsys):
    def fake_probe(names=None, timeout=10, client=None):
        return [
            ProbeResult("greenhouse", "acme", OK, "2 jobs"),
            ProbeResult("lever", "deadco", GONE, "HTTP 404"),
        ]

    monkeypatch.setattr("api_search.probe.probe_slugs", fake_probe)
    assert main(["probe-slugs"]) == 1  # a GONE slug fails the run
    out = capsys.readouterr().out
    assert "lever/deadco: GONE (HTTP 404)" in out
    assert "2 slugs probed — 1 OK, 0 EMPTY, 1 GONE, 0 ERROR" in out

    monkeypatch.setattr(
        "api_search.probe.probe_slugs",
        lambda names=None, timeout=10, client=None: [
            ProbeResult("greenhouse", "acme", OK, "2 jobs")
        ],
    )
    assert main(["probe-slugs"]) == 0


def test_main_probe_slugs_unknown_source_is_usage_error(config, capsys):
    assert main(["probe-slugs", "adzuna"]) == 2
    assert "adzuna" in capsys.readouterr().err
