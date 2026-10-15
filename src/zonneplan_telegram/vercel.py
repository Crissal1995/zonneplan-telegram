"""
Vercel entrypoint: exposes the Telegram webhook as a FastAPI (ASGI) application.

Vercel picks this module up through ``[tool.vercel] entrypoint`` in ``pyproject.toml``.
Telegram POSTs every update to ``/api/webhook``; the handler answers the command
synchronously so the response is complete before the function returns.
"""

from __future__ import annotations

import datetime
import importlib.util
import os
import secrets
from typing import TYPE_CHECKING, Annotated

from fastapi import FastAPI, Header, HTTPException, Query, status
from loguru import logger

from zonneplan_telegram.analytics import CommandEvent, build_summary, record_command
from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE
from zonneplan_telegram.commands import COMMANDS, ERROR_MESSAGE, HELP_MESSAGE, UNKNOWN_COMMAND, parse_command
from zonneplan_telegram.digest import send_daily_digest
from zonneplan_telegram.telegram import send_telegram_message

# FastAPI resolves the request-model annotation at runtime, so this import is not type-only.
from zonneplan_telegram.telegram.models import Update  # noqa: TC001

if TYPE_CHECKING:
    from zonneplan_telegram.telegram.models import User

# Load environment variables from .env file if python-dotenv is installed (local development only).
importlib.util.find_spec("dotenv") and importlib.import_module("dotenv").load_dotenv()

WEBHOOK_PATH = "/api/webhook"
DIGEST_PATH = "/api/digest"
ANALYTICS_PATH = "/api/analytics"
DEFAULT_DIGEST_HOUR = 6
HOURS_PER_DAY = 24

app = FastAPI(title="zonneplan-telegram", docs_url=None, redoc_url=None)


@app.get("/")
def health() -> dict[str, str]:
    """Reports that the function is reachable."""
    return {"status": "ok"}


@app.post(WEBHOOK_PATH)
def telegram_webhook(
    update: Update,
    secret_token: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> dict[str, bool]:
    """Validates a Telegram update and answers the command it contains."""
    expected_token = os.environ.get("TELEGRAM_WEBHOOK_SECRET")
    if expected_token and secret_token != expected_token:
        logger.warning("Rejected update {} with an invalid secret token.", update.update_id)
        detail = "Invalid secret token"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    message = update.message
    if message is None or message.text is None:
        return {"ok": True}

    chat_id = message.chat.id
    user = message.from_
    command = parse_command(message.text)
    if command is None:
        send_telegram_message(HELP_MESSAGE, chat_id=str(chat_id))
        return {"ok": True}

    handler = COMMANDS.get(command)
    if handler is None:
        _record(UNKNOWN_COMMAND, chat_id=chat_id, user=user, ok=True)
        send_telegram_message(HELP_MESSAGE, chat_id=str(chat_id))
        return {"ok": True}

    try:
        handler(chat_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to handle {} for chat {}.", command, chat_id)
        _record(command, chat_id=chat_id, user=user, ok=False)
        send_telegram_message(ERROR_MESSAGE, chat_id=str(chat_id))
        return {"ok": True}

    _record(command, chat_id=chat_id, user=user, ok=True)
    return {"ok": True}


def _record(command: str, *, chat_id: int, user: User | None, ok: bool) -> None:
    """Records one handled command in the analytics store."""
    record_command(
        CommandEvent(
            command=command,
            chat_id=chat_id,
            user_id=None if user is None else user.id,
            username=None if user is None else user.username,
            ok=ok,
        )
    )


@app.get(ANALYTICS_PATH)
def analytics_summary(
    secret: Annotated[str | None, Header(alias="X-Analytics-Secret")] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    """
    Returns the usage aggregates the Grafana dashboard renders.

    Protected by ``ANALYTICS_SECRET``. Grafana polls it through the Infinity data source,
    which sends the secret either as ``X-Analytics-Secret`` or as a bearer token.
    """
    expected_secret = os.environ.get("ANALYTICS_SECRET")
    if not expected_secret:
        logger.error("ANALYTICS_SECRET is not configured; rejecting the analytics request.")
        detail = "Analytics endpoint is not configured"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if not _matches_secret(expected_secret, secret, authorization):
        logger.warning("Rejected the analytics request with an invalid secret.")
        detail = "Invalid analytics secret"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    try:
        return build_summary()
    except Exception:  # noqa: BLE001
        logger.exception("Could not build the analytics summary.")
        detail = "The analytics store is not reachable"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail) from None


def _matches_secret(expected: str, header_value: str | None, authorization: str | None) -> bool:
    """Accepts the analytics secret as a dedicated header or as a bearer token."""
    if header_value is not None and secrets.compare_digest(header_value, expected):
        return True
    if authorization is None:
        return False
    scheme, _, token = authorization.partition(" ")
    return secrets.compare_digest(token or scheme, expected)


def _digest_hour() -> int:
    """Returns the configured digest hour in the market timezone, defaulting to 06:00."""
    raw = os.environ.get("DIGEST_HOUR")
    if raw is None:
        return DEFAULT_DIGEST_HOUR
    try:
        hour = int(raw)
    except ValueError:
        logger.warning("Ignoring non-numeric DIGEST_HOUR {!r}; using {}.", raw, DEFAULT_DIGEST_HOUR)
        return DEFAULT_DIGEST_HOUR
    if not 0 <= hour < HOURS_PER_DAY:
        logger.warning("Ignoring out-of-range DIGEST_HOUR {!r}; using {}.", raw, DEFAULT_DIGEST_HOUR)
        return DEFAULT_DIGEST_HOUR
    return hour


@app.api_route(DIGEST_PATH, methods=["GET", "POST"])
def send_digest(
    secret: Annotated[str | None, Header(alias="X-Digest-Secret")] = None,
    *,
    force: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    """
    Sends the daily digest. Meant to be called by an external scheduler.

    Runs only when the local hour in ``MARKET_TIMEZONE`` matches the configured digest hour, so
    the scheduler can ping hourly and the clock change is handled here instead of by the caller.
    """
    expected_secret = os.environ.get("DIGEST_SECRET")
    if not expected_secret:
        logger.error("DIGEST_SECRET is not configured; rejecting the digest trigger.")
        detail = "Digest trigger is not configured"
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    if secret != expected_secret:
        logger.warning("Rejected the digest trigger with an invalid secret.")
        detail = "Invalid digest secret"
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)

    local_hour = datetime.datetime.now(MARKET_TIMEZONE).hour
    if not force and local_hour != _digest_hour():
        logger.info("Skipping the digest: local hour {} is not the digest hour.", local_hour)
        return {"ok": True, "skipped": True, "sent": 0}

    sent = send_daily_digest()
    return {"ok": True, "skipped": False, "sent": sent}
