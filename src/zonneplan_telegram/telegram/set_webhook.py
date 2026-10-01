"""
CLI that registers (or removes) the Telegram webhook pointing at a deployment.

Usage::

    uv run set-webhook https://<project>.vercel.app

Requires ``TELEGRAM_BOT_TOKEN`` and, when setWebhook is protected, ``TELEGRAM_WEBHOOK_SECRET``.
"""

from __future__ import annotations

import argparse
import os
from typing import TYPE_CHECKING

import requests
from loguru import logger

from zonneplan_telegram.commands import BOT_COMMANDS

if TYPE_CHECKING:
    from typing import Any

API_BASE_URL = "https://api.telegram.org"
WEBHOOK_PATH = "/api/webhook"
REQUEST_TIMEOUT = 15


def _method_url(bot_token: str, method: str) -> str:
    return f"{API_BASE_URL}/bot{bot_token}/{method}"


def _call(method: str, bot_token: str, payload: dict[str, Any]) -> object:
    response = requests.post(_method_url(bot_token, method), json=payload, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    body = response.json()
    if not body.get("ok"):
        msg = f"Telegram rejected {method}: {body.get('description')}"
        raise RuntimeError(msg)
    return body.get("result")


def set_webhook(base_url: str, *, bot_token: str, secret_token: str | None = None) -> str:
    """Points Telegram at ``<base_url>/api/webhook`` and returns the registered URL."""
    url = f"{base_url.rstrip('/')}{WEBHOOK_PATH}"
    payload: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message"],
        "drop_pending_updates": True,
    }
    if secret_token:
        payload["secret_token"] = secret_token
    _call("setWebhook", bot_token, payload)
    return url


def delete_webhook(*, bot_token: str) -> None:
    """Removes the webhook so Telegram stops delivering updates."""
    _call("deleteWebhook", bot_token, {"drop_pending_updates": True})


def get_webhook_info(*, bot_token: str) -> object:
    """Returns the webhook status reported by Telegram."""
    return _call("getWebhookInfo", bot_token, {})


def set_my_commands(*, bot_token: str) -> int:
    """Publishes the command list shown in the Telegram menu and returns its size."""
    commands = [{"command": command, "description": description} for command, description in BOT_COMMANDS]
    _call("setMyCommands", bot_token, {"commands": commands})
    return len(commands)


def main() -> None:
    """Entry point of the ``set-webhook`` console script."""
    parser = argparse.ArgumentParser(description="Register the Telegram webhook with a deployment.")
    parser.add_argument("base_url", nargs="?", help="Public base URL, e.g. https://my-bot.vercel.app")
    parser.add_argument("--delete", action="store_true", help="Remove the webhook instead of registering it.")
    parser.add_argument("--info", action="store_true", help="Print the current webhook status and exit.")
    args = parser.parse_args()

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        raise SystemExit(1)

    if args.info:
        logger.info("Webhook info: {}", get_webhook_info(bot_token=bot_token))
        return

    if args.delete:
        delete_webhook(bot_token=bot_token)
        logger.info("Webhook deleted.")
        return

    if not args.base_url:
        parser.error("base_url is required unless --delete or --info is used.")

    url = set_webhook(args.base_url, bot_token=bot_token, secret_token=os.environ.get("TELEGRAM_WEBHOOK_SECRET"))
    logger.info("Webhook registered at {}", url)
    logger.info("Registered {} commands.", set_my_commands(bot_token=bot_token))


if __name__ == "__main__":
    main()
