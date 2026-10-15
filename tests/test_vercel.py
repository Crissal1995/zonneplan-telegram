"""
Tests for the webhook and the analytics endpoint.

The route functions are called directly, so the suite needs no ASGI client. Every test has
its credentials stripped by ``conftest`` and its Telegram clients replaced here, so nothing
leaves the machine.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from zonneplan_telegram import commands, vercel
from zonneplan_telegram.telegram.models import Update

SENT: list[str] = []
"""Every message a test tried to send, captured by the ``_silence_telegram`` fixture."""


def _record(message: str, **_kwargs: object) -> None:
    """Captures an outgoing Telegram message."""
    SENT.append(message)


@pytest.fixture(autouse=True)
def _silence_telegram(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Routes both Telegram clients to the recorder.

    ``commands`` owns the handler replies and ``vercel`` the fallbacks, so both have to be
    replaced: patching only one still lets the other reach the real Bot API.
    """
    SENT.clear()
    monkeypatch.setattr(commands, "send_telegram_message", _record)
    monkeypatch.setattr(vercel, "send_telegram_message", _record)


def _update(text: str) -> Update:
    """Builds a synthetic Telegram update carrying ``text``."""
    return Update.model_validate(
        {
            "update_id": 1,
            "message": {
                "chat": {"id": 7},
                "text": text,
                "from": {"id": 42, "username": "ann"},
            },
        }
    )


def _boom(_chat_id: int) -> None:
    """A command handler that always fails."""
    msg = "boom"
    raise ValueError(msg)


def _summary() -> dict[str, object]:
    """Stands in for the real aggregate builder."""
    return {"totals": {"users": 1}}


def test_webhook_records_a_known_command(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[vercel.CommandEvent] = []
    monkeypatch.setattr(vercel, "record_command", recorded.append)

    assert vercel.telegram_webhook(_update("/help")) == {"ok": True}

    assert recorded == [vercel.CommandEvent(command="/help", chat_id=7, user_id=42, username="ann", ok=True)]
    assert SENT == [commands.HELP_MESSAGE]


def test_webhook_normalizes_the_command_before_handling_and_recording(monkeypatch: pytest.MonkeyPatch) -> None:
    handled: list[int] = []
    recorded: list[vercel.CommandEvent] = []
    monkeypatch.setattr(vercel, "record_command", recorded.append)
    monkeypatch.setitem(vercel.COMMANDS, "/pricenow", handled.append)

    assert vercel.telegram_webhook(_update("/priceNow@MyBot")) == {"ok": True}

    assert handled == [7]
    assert [event.command for event in recorded] == ["/pricenow"]


def test_webhook_records_unknown_commands_in_their_own_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[vercel.CommandEvent] = []
    monkeypatch.setattr(vercel, "record_command", recorded.append)

    assert vercel.telegram_webhook(_update("/nope")) == {"ok": True}

    assert [event.command for event in recorded] == [vercel.UNKNOWN_COMMAND]
    assert SENT == [commands.HELP_MESSAGE]


def test_webhook_records_a_failed_handler(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[vercel.CommandEvent] = []
    monkeypatch.setattr(vercel, "record_command", recorded.append)
    monkeypatch.setitem(vercel.COMMANDS, "/help", _boom)

    assert vercel.telegram_webhook(_update("/help")) == {"ok": True}

    assert [(event.command, event.ok) for event in recorded] == [("/help", False)]
    assert SENT == [commands.ERROR_MESSAGE]


def test_webhook_ignores_plain_text(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: list[vercel.CommandEvent] = []
    monkeypatch.setattr(vercel, "record_command", recorded.append)

    assert vercel.telegram_webhook(_update("hello")) == {"ok": True}

    assert recorded == []
    assert SENT == [commands.HELP_MESSAGE]


def test_webhook_rejects_an_invalid_secret_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected")

    with pytest.raises(HTTPException) as error:
        vercel.telegram_webhook(_update("/help"), secret_token="wrong")

    assert error.value.status_code == 401


def test_analytics_endpoint_is_unavailable_without_a_secret() -> None:
    with pytest.raises(HTTPException) as error:
        vercel.analytics_summary()

    assert error.value.status_code == 503


def test_analytics_endpoint_rejects_a_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYTICS_SECRET", "s3cret")

    with pytest.raises(HTTPException) as error:
        vercel.analytics_summary(secret="nope")

    assert error.value.status_code == 401


def test_analytics_endpoint_accepts_the_header_and_a_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYTICS_SECRET", "s3cret")
    monkeypatch.setattr(vercel, "build_summary", _summary)

    assert vercel.analytics_summary(secret="s3cret") == {"totals": {"users": 1}}
    assert vercel.analytics_summary(authorization="Bearer s3cret") == {"totals": {"users": 1}}


def test_analytics_endpoint_reports_an_unreachable_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANALYTICS_SECRET", "s3cret")

    def _broken() -> dict[str, object]:
        msg = "redis is down"
        raise RuntimeError(msg)

    monkeypatch.setattr(vercel, "build_summary", _broken)

    with pytest.raises(HTTPException) as error:
        vercel.analytics_summary(secret="s3cret")

    assert error.value.status_code == 503
