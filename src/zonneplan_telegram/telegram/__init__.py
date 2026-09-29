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


def send_telegram_message(
    message: str,
    *,
    chat_id: str | None = None,
    bot_token: SecretStr | str | None = None,
) -> None:
    chat_id = get_var(chat_id, "TELEGRAM_CHAT_ID")
    bot_token = get_var(bot_token, "TELEGRAM_BOT_TOKEN")
    if bot_token is None or chat_id is None:
        msg = "Both bot_token and chat_id must be provided."
        raise ValueError(msg)

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    logger.info("Sending message to Telegram.")
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()


def send_telegram_photo(
    photo_path: str | Path, caption: str, *, chat_id: str | None = None, bot_token: SecretStr | str | None = None
) -> None:
    chat_id = get_var(chat_id, "TELEGRAM_CHAT_ID")
    bot_token = get_var(bot_token, "TELEGRAM_BOT_TOKEN")
    if bot_token is None or chat_id is None:
        msg = "Both bot_token and chat_id must be provided."
        raise ValueError(msg)

    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"

    photo_bytes = Path(photo_path).read_bytes()
    payload = {
        "chat_id": chat_id,
        "caption": caption,
        "parse_mode": "Markdown",
    }
    files = {"photo": photo_bytes}
    response = requests.post(url, data=payload, files=files, timeout=15)
    response.raise_for_status()
