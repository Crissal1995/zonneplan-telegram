"""
Subscription store for the daily digest.

The Vercel filesystem is read-only, so the set of subscribed chat ids lives in an Upstash
Redis database reached through its REST API. ``requests`` is already a runtime dependency,
so no extra client library is needed.
"""

from __future__ import annotations

import os

import requests
from loguru import logger

REQUEST_TIMEOUT = 10
SUBSCRIBERS_KEY = "zonneplan-telegram:digest-subscribers"


def _redis_command(command: list[str]) -> object:
    """Runs a single Redis command through the Upstash REST API and returns its result."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        msg = "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must both be set."
        raise RuntimeError(msg)
    response = requests.post(url, json=command, headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json().get("result")


def add_subscriber(chat_id: int | str) -> None:
    """Adds ``chat_id`` to the set of digest subscribers."""
    _redis_command(["SADD", SUBSCRIBERS_KEY, str(chat_id)])


def remove_subscriber(chat_id: int | str) -> None:
    """Removes ``chat_id`` from the set of digest subscribers."""
    _redis_command(["SREM", SUBSCRIBERS_KEY, str(chat_id)])


def get_subscribers() -> set[str]:
    """
    Returns the chat ids subscribed to the daily digest.

    Falls back to an empty set (and logs a warning) when the Upstash credentials are not
    configured, so a missing subscription store never breaks the digest trigger.
    """
    try:
        members = _redis_command(["SMEMBERS", SUBSCRIBERS_KEY])
    except RuntimeError:
        logger.warning("Digest subscriptions are not configured; no subscribers returned.")
        return set()
    if not isinstance(members, list):
        return set()
    return {str(member) for member in members}
