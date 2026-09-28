import os

import requests
from loguru import logger
from pydantic import SecretStr


def send_telegram_message(
    message: str,
    chat_id: str | None = None,
    bot_token: SecretStr | str | None = None,
) -> None:
    if isinstance(bot_token, SecretStr):
        bot_token = bot_token.get_secret_value()
    if bot_token is None:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if chat_id is None:
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")

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
    requests.post(url, json=payload, timeout=30)
