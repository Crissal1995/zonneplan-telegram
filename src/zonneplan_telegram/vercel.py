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
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, Query, status
from loguru import logger

from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE
from zonneplan_telegram.commands import COMMANDS, ERROR_MESSAGE, HELP_MESSAGE, parse_command
from zonneplan_telegram.digest import send_daily_digest
from zonneplan_telegram.telegram import send_telegram_message

# FastAPI resolves the request-model annotation at runtime, so this import is not type-only.
from zonneplan_telegram.telegram.models import Update  # noqa: TC001

# Load environment variables from .env file if python-dotenv is installed (local development only).
importlib.util.find_spec("dotenv") and importlib.import_module("dotenv").load_dotenv()

WEBHOOK_PATH = "/api/webhook"
DIGEST_PATH = "/api/digest"
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
    command = parse_command(message.text)
    handler = COMMANDS.get(command) if command is not None else None
    if handler is None:
        send_telegram_message(HELP_MESSAGE, chat_id=str(chat_id))
        return {"ok": True}

    try:
        handler(chat_id)
    except Exception:  # noqa: BLE001
        logger.exception("Failed to handle {} for chat {}.", command, chat_id)
        send_telegram_message(ERROR_MESSAGE, chat_id=str(chat_id))

    return {"ok": True}


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
