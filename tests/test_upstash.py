"""
Tests for the shared Upstash REST client.

``requests.post`` is replaced, so the suite never talks to Redis.
"""

from __future__ import annotations

import pytest

from zonneplan_telegram import upstash

BASE_URL = "https://example.upstash.io"


class _FakeResponse:
    """Stand-in for ``requests.Response``."""

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        """Never fails: the tests only exercise successful HTTP responses."""

    def json(self) -> object:
        """Returns the canned payload."""
        return self._payload


def _install(monkeypatch: pytest.MonkeyPatch, payload: object) -> dict[str, object]:
    """Sets the credentials and captures the next POST request."""
    captured: dict[str, object] = {}

    def fake_post(url: str, *, json: object, headers: dict[str, str], timeout: int) -> _FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeResponse(payload)

    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", BASE_URL)
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")
    monkeypatch.setattr(upstash.requests, "post", fake_post)
    return captured


def test_redis_command_posts_the_command_and_returns_the_result(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch, {"result": 7})

    assert upstash.redis_command(["INCR", "counter"]) == 7
    assert captured["url"] == BASE_URL
    assert captured["json"] == ["INCR", "counter"]
    assert captured["headers"] == {"Authorization": "Bearer test-token"}


def test_redis_command_returns_none_when_redis_reports_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, {"error": "ERR wrong type"})

    assert upstash.redis_command(["GET", "counter"]) is None


def test_redis_pipeline_posts_a_two_dimensional_array(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _install(monkeypatch, [{"result": "OK"}, {"result": [1, 2]}])

    assert upstash.redis_pipeline([["SET", "a", "b"], ["LRANGE", "l", "0", "-1"]]) == ["OK", [1, 2]]
    assert captured["url"] == f"{BASE_URL}/pipeline"
    assert captured["json"] == [["SET", "a", "b"], ["LRANGE", "l", "0", "-1"]]


def test_redis_pipeline_keeps_the_reply_order_and_maps_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, [{"result": 1}, {"error": "ERR boom"}, {"result": 3}])

    assert upstash.redis_pipeline([["A"], ["B"], ["C"]]) == [1, None, 3]


def test_redis_pipeline_short_circuits_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)

    assert upstash.redis_pipeline([]) == []


def test_missing_credentials_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "test-token")

    with pytest.raises(RuntimeError, match="UPSTASH_REDIS_REST_URL"):
        upstash.redis_command(["PING"])
