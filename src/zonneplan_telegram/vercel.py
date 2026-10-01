"""
Vercel entrypoint: exposes the Telegram webhook as a FastAPI (ASGI) application.

Vercel picks this module up through ``[tool.vercel] entrypoint`` in ``pyproject.toml``.
Telegram POSTs every update to ``/api/webhook``; the handler answers the command
synchronously so the response is complete before the function returns.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Annotated

from fastapi import FastAPI, Header, HTTPException, status
from loguru import logger

from zonneplan_telegram.commands import COMMANDS, ERROR_MESSAGE, HELP_MESSAGE, parse_command
from zonneplan_telegram.telegram import is_chat_allowed, send_telegram_message

# FastAPI resolves the request-model annotation at runtime, so this import is not type-only.
from zonneplan_telegram.telegram.models import Update  # noqa: TC001

# Load environment variables from .env file if python-dotenv is installed (local development only).
importlib.util.find_spec("dotenv") and importlib.import_module("dotenv").load_dotenv()

WEBHOOK_PATH = "/api/webhook"

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
    if not is_chat_allowed(chat_id):
        logger.warning("Ignored update {} from chat {}.", update.update_id, chat_id)
        return {"ok": True}

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
