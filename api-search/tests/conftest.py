"""Shared fakes for HTTP-dependent tests."""

from collections.abc import Callable
from unittest.mock import MagicMock

import httpx
import pytest


class FakeResp:
    def __init__(self, payload, status: int = 200, text: str = ""):
        self._payload = payload
        self.status = status
        self.text = text

    def raise_for_status(self):
        if self.status >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self):
        return self._payload


def make_client(route: Callable[[str, dict | None], FakeResp]) -> MagicMock:
    """A fake httpx.Client whose .get(url, params=...) is resolved by `route`."""
    client = MagicMock()
    client.__enter__ = MagicMock(return_value=client)
    client.__exit__ = MagicMock(return_value=False)
    client.get.side_effect = lambda url, params=None: route(url, params)
    return client


@pytest.fixture
def adzuna_env(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_API_KEY", "test_key")
