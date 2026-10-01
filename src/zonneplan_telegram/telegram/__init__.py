import os
from pathlib import Path

import requests
from loguru import logger
from pydantic import SecretStr


def get_var(value: str | SecretStr | None, env_var: str) -> str | None:
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    if value is not None:
        return value
    return os.environ.get(env_var)


def get_allowed_chat_ids() -> set[str]:
    """
    Returns the chat ids the bot is allowed to serve.

    Reads the comma-separated ``TELEGRAM_ALLOWED_CHAT_IDS`` variable and falls back to the
    single ``TELEGRAM_CHAT_ID``.
    """
    raw = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS") or os.environ.get("TELEGRAM_CHAT_ID") or ""
    return {chat_id.strip() for chat_id in raw.split(",") if chat_id.strip()}


def is_chat_allowed(chat_id: int | str) -> bool:
    """
    Returns whether ``chat_id`` is part of the configured allowlist.

    An empty allowlist denies every chat, so the bot never answers by accident.
    """
    return str(chat_id) in get_allowed_chat_ids()


def _resolve_credentials(chat_id: str | None, bot_token: SecretStr | str | None) -> tuple[str, str]:
    """Resolves the chat id and bot token, preferring explicit arguments over the environment."""
    resolved_chat_id = get_var(chat_id, "TELEGRAM_CHAT_ID")
    resolved_bot_token = get_var(bot_token, "TELEGRAM_BOT_TOKEN")
    if resolved_chat_id is None or resolved_bot_token is None:
        msg = "Both bot_token and chat_id must be provided."
        raise ValueError(msg)
    return resolved_chat_id, resolved_bot_token


def send_telegram_message(
    message: str,
    *,
    chat_id: str | None = None,
    bot_token: SecretStr | str | None = None,
) -> None:
    resolved_chat_id, resolved_bot_token = _resolve_credentials(chat_id, bot_token)

    url = f"https://api.telegram.org/bot{resolved_bot_token}/sendMessage"
    payload = {
        "chat_id": resolved_chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    logger.info("Sending message to Telegram.")
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()


def send_telegram_document(
    document_path: str | Path,
    caption: str,
    *,
    chat_id: str | None = None,
    bot_token: SecretStr | str | None = None,
) -> None:
    """
    Sends a local file with ``sendDocument``.

    Telegram only accepts raster images for ``sendPhoto``, so SVG charts are delivered
    as a document instead.
    """
    resolved_chat_id, resolved_bot_token = _resolve_credentials(chat_id, bot_token)

    url = f"https://api.telegram.org/bot{resolved_bot_token}/sendDocument"
    document = Path(document_path)
    payload = {
        "chat_id": resolved_chat_id,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    files = {"document": (document.name, document.read_bytes())}
    logger.info("Sending document {} to Telegram.", document.name)
    response = requests.post(url, data=payload, files=files, timeout=30)
    response.raise_for_status()
