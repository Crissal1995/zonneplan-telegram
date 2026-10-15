"""
Subscription store for the daily digest.

The Vercel filesystem is read-only, so the set of subscribed chat ids lives in an Upstash
Redis database reached through its REST API. The transport is shared with the analytics
store (``zonneplan_telegram.upstash``), so both stores need the same two credentials.
"""

from __future__ import annotations

from loguru import logger

from zonneplan_telegram.upstash import redis_command

SUBSCRIBERS_KEY = "zonneplan-telegram:digest-subscribers"


def add_subscriber(chat_id: int | str) -> None:
    """Adds ``chat_id`` to the set of digest subscribers."""
    redis_command(["SADD", SUBSCRIBERS_KEY, str(chat_id)])


def remove_subscriber(chat_id: int | str) -> None:
    """Removes ``chat_id`` from the set of digest subscribers."""
    redis_command(["SREM", SUBSCRIBERS_KEY, str(chat_id)])


def get_subscribers() -> set[str]:
    """
    Returns the chat ids subscribed to the daily digest.

    Falls back to an empty set (and logs a warning) when the Upstash credentials are not
    configured, so a missing subscription store never breaks the digest trigger.
    """
    try:
        members = redis_command(["SMEMBERS", SUBSCRIBERS_KEY])
    except RuntimeError:
        logger.warning("Digest subscriptions are not configured; no subscribers returned.")
        return set()
    if not isinstance(members, list):
        return set()
    return {str(member) for member in members}
