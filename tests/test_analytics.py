"""
Tests for the usage analytics aggregates.

The Redis pipeline is replaced by a fake that answers per key, so the suite stays offline
and the payload the Grafana dashboard consumes is asserted directly.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from zonneplan_telegram import analytics
from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE

if TYPE_CHECKING:
    import pytest

DAILY_KEY_PREFIX = f"{analytics.PREFIX}:daily"
USER_KEY_PREFIX = f"{analytics.PREFIX}:user"


def _today() -> str:
    """Returns today in the market timezone, the way the module buckets events."""
    return dt.datetime.now(MARKET_TIMEZONE).date().isoformat()


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[list[list[str]]]:
    """Replaces the write pipeline with a recorder and returns the captured calls."""
    calls: list[list[list[str]]] = []

    def fake_pipeline(commands: list[list[str]]) -> list[object]:
        calls.append(commands)
        return []

    monkeypatch.setattr(analytics, "redis_pipeline", fake_pipeline)
    return calls


def test_record_command_folds_every_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    today = _today()

    analytics.record_command(analytics.CommandEvent(command="/pricenow", chat_id=1, user_id=42, username="ann"))

    commands = calls[0]
    assert commands[0][0] == "XADD"
    assert ["HINCRBY", analytics.TOTALS_KEY, "commands", "1"] in commands
    assert ["HINCRBY", analytics.TOTALS_KEY, "cmd:/pricenow", "1"] in commands
    assert ["HINCRBY", f"{DAILY_KEY_PREFIX}:{today[:7]}", f"d:{today}:c", "1"] in commands
    assert ["SADD", f"{analytics.PREFIX}:users:day:{today}", "42"] in commands
    assert ["SADD", analytics.ALL_USERS_KEY, "42"] in commands
    assert ["ZINCRBY", analytics.USER_COMMANDS_KEY, "1", "42"] in commands
    assert ["HSETNX", f"{USER_KEY_PREFIX}:42", "first_seen"] == commands[-1][:3]
    assert not any("errors" in command for command in commands)


def test_record_command_records_the_hour_to_build_the_peak_hour_view(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    today = _today()

    analytics.record_command(analytics.CommandEvent(command="/chart", chat_id=1, user_id=42))

    hour_fields = [command[2] for command in calls[0] if ":h:" in command[2]]
    assert len(hour_fields) == 1
    assert hour_fields[0].startswith(f"d:{today}:h:")
    assert hour_fields[0].removeprefix(f"d:{today}:h:").isdigit()


def test_record_command_counts_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    today = _today()

    analytics.record_command(analytics.CommandEvent(command="/chart", chat_id=1, user_id=42, ok=False))

    commands = calls[0]
    assert ["HINCRBY", analytics.TOTALS_KEY, "errors", "1"] in commands
    assert ["HINCRBY", f"{DAILY_KEY_PREFIX}:{today[:7]}", f"d:{today}:e", "1"] in commands


def test_record_command_without_a_user_skips_the_user_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)

    analytics.record_command(analytics.CommandEvent(command="/help", chat_id=1))

    commands = calls[0]
    assert commands[0][0] == "XADD"
    assert not any(command[0] in {"SADD", "ZINCRBY", "HSET", "HSETNX"} for command in commands)


def test_record_command_swallows_redis_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_commands: list[list[str]]) -> list[object]:
        msg = "redis is down"
        raise RuntimeError(msg)

    monkeypatch.setattr(analytics, "redis_pipeline", boom)

    # Must not raise: analytics never break a reply.
    analytics.record_command(analytics.CommandEvent(command="/help", chat_id=1, user_id=42))


def test_record_digest_ignores_empty_fan_outs(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)

    analytics.record_digest(0)

    assert calls == []


def test_record_digest_counts_the_delivered_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _capture(monkeypatch)
    today = _today()

    analytics.record_digest(3)

    assert ["HINCRBY", f"{DAILY_KEY_PREFIX}:{today[:7]}", f"d:{today}:ds", "3"] in calls[0]
    assert ["HINCRBY", analytics.TOTALS_KEY, "digest", "3"] in calls[0]


def _install_summary_fakes(monkeypatch: pytest.MonkeyPatch, today: str) -> None:
    """Installs an empty cache and a pipeline that answers per key, so a payload can be built."""
    hashes: dict[str, dict[str, str]] = {
        analytics.TOTALS_KEY: {"commands": "9", "errors": "2", "digest": "3", "cmd:/chart": "5", "cmd:/help": "4"},
        f"{DAILY_KEY_PREFIX}:{today[:7]}": {
            f"d:{today}:c": "9",
            f"d:{today}:e": "2",
            f"d:{today}:ds": "3",
            f"d:{today}:h:09": "7",
        },
        f"{USER_KEY_PREFIX}:42": {"username": "ann", "first_seen": "1700000000", "last_seen": "1700000100"},
    }
    counters = {f"{analytics.PREFIX}:users:day:{today}": 4, analytics.ALL_USERS_KEY: 6}

    def fake_command(_command: list[str]) -> object:
        return None  # an empty cache, so the payload is actually built

    def fake_pipeline(commands: list[list[str]]) -> list[object]:
        replies: list[object] = []
        for command in commands:
            if command[0] == "HGETALL":
                # Upstash serialises HGETALL as a flat ["field", "value", ...] array, not an object.
                fields = hashes.get(command[1], {})
                replies.append([item for pair in fields.items() for item in pair])
            elif command[0] == "SCARD":
                replies.append(counters.get(command[1], 0))
            elif command[0] == "ZREVRANGE":
                replies.append(["42", "5"])
            else:
                replies.append(None)
        return replies

    monkeypatch.setattr(analytics, "redis_command", fake_command)
    monkeypatch.setattr(analytics, "redis_pipeline", fake_pipeline)


def test_build_summary_renders_the_all_time_totals(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_summary_fakes(monkeypatch, _today())

    payload = analytics.build_summary()

    assert payload["totals"] == {"users": 6, "commands": 9, "errors": 2, "digest_sent": 3}
    assert payload["commands"] == [{"command": "/chart", "count": 5}, {"command": "/help", "count": 4}]


def test_build_summary_renders_the_activity_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    today = _today()
    _install_summary_fakes(monkeypatch, today)

    payload = analytics.build_summary()

    daily = payload["daily"]
    assert isinstance(daily, list)
    assert len(daily) == 30
    last = daily[-1]
    assert isinstance(last, dict)
    assert last["date"] == today
    assert last["commands"] == 9
    assert last["errors"] == 2
    assert last["users"] == 4
    assert last["digest_sent"] == 3

    hourly = payload["hourly"]
    assert isinstance(hourly, list)
    assert len(hourly) == 24
    nine = hourly[9]
    assert isinstance(nine, dict)
    assert nine["count"] == 7

    weekly = payload["weekly"]
    assert isinstance(weekly, list)
    assert len(weekly) == 12

    monthly = payload["monthly"]
    assert isinstance(monthly, list)
    assert len(monthly) == 12


def test_build_summary_renders_the_top_users(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_summary_fakes(monkeypatch, _today())

    payload = analytics.build_summary()

    users = payload["users"]
    assert isinstance(users, list)
    top = users[0]
    assert isinstance(top, dict)
    assert top["user_id"] == 42
    assert top["username"] == "ann"
    assert top["commands"] == 5
    assert top["first_seen"] == "2023-11-14T22:13:20+00:00"
