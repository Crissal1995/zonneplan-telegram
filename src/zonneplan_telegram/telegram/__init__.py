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


def _resolve_bot_token(bot_token: SecretStr | str | None) -> str:
    """Resolves the bot token, preferring an explicit argument over the environment."""
    resolved_bot_token = get_var(bot_token, "TELEGRAM_BOT_TOKEN")
    if resolved_bot_token is None:
        msg = "A bot token must be provided."
        raise ValueError(msg)
    return resolved_bot_token


def send_telegram_message(
    message: str,
    *,
    chat_id: str,
    bot_token: SecretStr | str | None = None,
) -> None:
    resolved_bot_token = _resolve_bot_token(bot_token)

    url = f"https://api.telegram.org/bot{resolved_bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    logger.info("Sending message to Telegram.")
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()


def send_telegram_photo(
    photo_path: str | Path,
    caption: str,
    *,
    chat_id: str,
    bot_token: SecretStr | str | None = None,
) -> None:
    """Sends a local image with ``sendPhoto`` so Telegram renders it inline."""
    resolved_bot_token = _resolve_bot_token(bot_token)

    url = f"https://api.telegram.org/bot{resolved_bot_token}/sendPhoto"
    photo = Path(photo_path)
    payload = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    files = {"photo": (photo.name, photo.read_bytes())}
    logger.info("Sending photo {} to Telegram.", photo.name)
    response = requests.post(url, data=payload, files=files, timeout=30)
    response.raise_for_status()
