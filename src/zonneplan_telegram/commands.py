"""
Telegram commands answered by the webhook.

Each handler receives the id of the chat that asked and replies through the
``zonneplan_telegram.telegram`` client. Handlers fetch the prices on every call so
the answers always reflect the current Zonneplan tariffs.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from zonneplan_telegram.api.hourly_prices import get_zonneplan_hourly_prices
from zonneplan_telegram.chart import generate_zonneplan_bar_chart
from zonneplan_telegram.telegram import send_telegram_document, send_telegram_message

if TYPE_CHECKING:
    from collections.abc import Callable

HELP_MESSAGE = """⚡ **Zonneplan - Energy Prices** ⚡

Available commands:

• /priceNow - Current hourly rate
• /priceTomorrow - Summary of tomorrow's prices
• /chart - Hourly price chart
• /help - Show this message"""

ERROR_MESSAGE = "⚠️ *Could not fetch the Zonneplan prices. Please try again in a few minutes.*"

# Commands published to Telegram: names must be lowercase, digits and underscores.
BOT_COMMANDS: list[tuple[str, str]] = [
    ("pricenow", "Current hourly rate"),
    ("pricetomorrow", "Summary of tomorrow's prices"),
    ("chart", "Hourly price chart"),
    ("help", "Show the available commands"),
]


def parse_command(text: str) -> str | None:
    """
    Extracts a normalized command from a message text.

    ``/priceNow@MyBot something`` becomes ``/pricenow``; text that is not a command
    returns ``None``.
    """
    if not text.startswith("/"):
        return None
    command = text.split(maxsplit=1)[0].split("@", maxsplit=1)[0]
    return command.lower()


def handle_help(chat_id: int) -> None:
    """Replies with the list of available commands."""
    send_telegram_message(HELP_MESSAGE, chat_id=str(chat_id))


def handle_price_now(chat_id: int) -> None:
    """Replies with the tariff of the current hour."""
    response = get_zonneplan_hourly_prices()
    send_telegram_message(response.as_price_now_markdown(), chat_id=str(chat_id))


def handle_price_tomorrow(chat_id: int) -> None:
    """Replies with tomorrow's price summary."""
    response = get_zonneplan_hourly_prices()
    send_telegram_message(response.as_tomorrow_markdown(), chat_id=str(chat_id))


def handle_chart(chat_id: int) -> None:
    """Renders today's hourly price chart (00:00-23:59) and sends it as an SVG document."""
    response = get_zonneplan_hourly_prices()
    output_path = Path(tempfile.gettempdir()) / f"zonneplan-chart-{chat_id}.svg"
    generate_zonneplan_bar_chart(response.get_today_prices(), output_path=str(output_path))
    send_telegram_document(
        document_path=output_path,
        caption="Zonneplan hourly price chart",
        chat_id=str(chat_id),
    )


COMMANDS: dict[str, Callable[[int], None]] = {
    "/start": handle_help,
    "/help": handle_help,
    "/pricenow": handle_price_now,
    "/pricetomorrow": handle_price_tomorrow,
    "/chart": handle_chart,
}
