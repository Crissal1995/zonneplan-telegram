"""
Minimal Upstash Redis REST client.

Upstash serves Redis over HTTP, which suits the serverless Vercel functions: no TCP
connection has to be kept alive between invocations. ``requests`` is already a runtime
dependency, so no extra Redis client library is needed.

Two shapes of calls are supported: a single command, and a pipeline that runs several
commands within one HTTP round trip. The pipeline keeps the write path of the analytics
store cheap, because the whole event is folded into the aggregates with a single request.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import requests
from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Sequence

    from requests._types import JsonType

REQUEST_TIMEOUT = 10


def _credentials() -> tuple[str, str]:
    """Returns the Upstash REST endpoint and token from the environment."""
    url = os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if not url or not token:
        msg = "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must both be set."
        raise RuntimeError(msg)
    return url, token


def _post(path: str, payload: JsonType) -> object:
    """Posts a command body to the Upstash REST API and returns the decoded JSON."""
    url, token = _credentials()
    response = requests.post(
        f"{url}{path}",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _unwrap(entry: object) -> object:
    """Extracts the ``result`` of one command, logging (and discarding) an ``error``."""
    if isinstance(entry, dict):
        error = entry.get("error")
        if error is not None:
            logger.warning("Upstash command failed: {}", error)
            return None
        return entry.get("result")
    return entry


def redis_command(command: Sequence[str]) -> object:
    """Runs a single Redis command through the Upstash REST API and returns its result."""
    return _unwrap(_post("", list(command)))


def redis_pipeline(commands: Sequence[Sequence[str]]) -> list[object]:
    """
    Runs several commands in one HTTP request and returns their results in order.

    A pipeline is not a transaction: the commands run in order, but commands sent by other
    clients may interleave with them.
    """
    if not commands:
        return []
    results = _post("/pipeline", [list(command) for command in commands])
    if not isinstance(results, list):
        return []
    return [_unwrap(entry) for entry in results]
