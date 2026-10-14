"""
Daily digest: today's cheapest hour and cheapest contiguous window.

The message is built once and fanned out to every subscribed chat. Delivery is triggered
from outside the application (an external scheduler calls ``/api/digest``), because neither
Vercel nor the Telegram webhook can schedule their own work.
"""

from __future__ import annotations

from loguru import logger

from zonneplan_telegram.api.hourly_prices import get_zonneplan_hourly_prices
from zonneplan_telegram.subscriptions import get_subscribers
from zonneplan_telegram.telegram import send_telegram_message


def build_daily_digest() -> str:
    """Fetches the prices and renders the daily digest message."""
    return get_zonneplan_hourly_prices().as_daily_digest_markdown()


def send_daily_digest() -> int:
    """Sends the digest to every subscribed chat and returns the recipient count."""
    recipients = get_subscribers()
    if not recipients:
        logger.info("No digest recipients (nobody subscribed); nothing sent.")
        return 0

    digest = build_daily_digest()
    for chat_id in sorted(recipients):
        send_telegram_message(digest, chat_id=chat_id)
    logger.info("Sent the daily digest to {} chat(s).", len(recipients))
    return len(recipients)
