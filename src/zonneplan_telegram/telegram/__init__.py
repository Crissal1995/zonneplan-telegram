import requests
import os
from pydantic import SecretStr

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")



def send_telegram_message(message: str | Markdown, chat_id: str, bot_token: SecretStr | str) -> None:
    if isinstance(bot_token, SecretStr):
        bot_token = bot_token.get_secret_value()
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }
    requests.post(url, json=payload)
