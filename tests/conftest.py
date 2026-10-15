"""
Shared fixtures for the offline test suite.

Importing ``zonneplan_telegram.vercel`` loads the local ``.env`` when ``python-dotenv`` is
installed, so a developer's real credentials would otherwise be visible to every test.
They are stripped here: a test that forgets to fake a client then fails fast instead of
reaching the live Telegram or Upstash services.
"""

from __future__ import annotations

import pytest

CREDENTIAL_NAMES = (
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
    "UPSTASH_REDIS_REST_URL",
    "UPSTASH_REDIS_REST_TOKEN",
    "DIGEST_SECRET",
    "ANALYTICS_SECRET",
)


@pytest.fixture(autouse=True)
def _without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Removes every real credential for the duration of a test."""
    for name in CREDENTIAL_NAMES:
        monkeypatch.delenv(name, raising=False)
