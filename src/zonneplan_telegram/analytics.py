"""
Usage analytics for the Telegram bot.

Every command the webhook answers is folded into the Upstash Redis database that already
stores the digest subscribers, so tracking needs no extra infrastructure. Recording is
best effort: a missing or failing Redis must never break a reply.

Storage layout, all keys prefixed with ``zonneplan-telegram:analytics``:

=========================  ===========================================================
``events``                 capped stream with the raw events (drill-down / manual queries)
``daily:<YYYY-MM>``        hash, one field per day and metric (commands, errors, hours)
``totals``                 hash with the all-time counters, including ``cmd:<name>``
``users:day:<date>``       set of the user ids seen that day
``users:week:<YYYY-Www>``  set of the user ids seen that ISO week
``users:month:<YYYY-MM>``  set of the user ids seen that month
``users:all``              set of every user id ever seen
``user:<id>``              hash with ``username`` / ``first_seen`` / ``last_seen``
``user-commands``          sorted set ranking the users by the number of commands
``summary``                short-lived cache of the payload served to the dashboard
=========================  ===========================================================

Days and hours are bucketed in ``MARKET_TIMEZONE`` (``Europe/Amsterdam``), the timezone the
bot already uses for the digest. Vercel runs in UTC, so bucketing on the host clock would
shift the daily and hourly aggregates by the DST offset.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from zonneplan_telegram.api.hourly_prices.model import MARKET_TIMEZONE
from zonneplan_telegram.upstash import redis_command, redis_pipeline

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

PREFIX = "zonneplan-telegram:analytics"
EVENTS_KEY = f"{PREFIX}:events"
TOTALS_KEY = f"{PREFIX}:totals"
ALL_USERS_KEY = f"{PREFIX}:users:all"
USER_COMMANDS_KEY = f"{PREFIX}:user-commands"
SUMMARY_KEY = f"{PREFIX}:summary"
COMMAND_FIELD_PREFIX = "cmd:"

# The stream is a bounded tail of the traffic: the aggregates below are the source of truth.
EVENTS_MAXLEN = 10_000
# Two years keeps every trend the dashboard renders (12 months) comfortably in range.
HISTORY_TTL_SECONDS = 60 * 60 * 24 * 730
SUMMARY_TTL_SECONDS = 60
HOURS_PER_DAY = 24

DEFAULT_DAYS = 30
DEFAULT_WEEKS = 12
DEFAULT_MONTHS = 12
DEFAULT_TOP_USERS = 10


@dataclass(frozen=True, slots=True)
class CommandEvent:
    """One command answered by the webhook."""

    command: str
    chat_id: int
    user_id: int | None = None
    username: str | None = None
    ok: bool = True


def record_command(event: CommandEvent) -> None:
    """Folds a command event into the aggregates. Never raises."""
    now = _now()
    try:
        redis_pipeline(_event_commands(event, now))
    except Exception:  # noqa: BLE001
        logger.warning("Could not record the analytics event for {}.", event.command)


def record_digest(sent: int) -> None:
    """Records how many digest messages were delivered today. Never raises."""
    if sent <= 0:
        return
    now = _now()
    day = now.date().isoformat()
    try:
        redis_pipeline(
            [
                ["HINCRBY", _daily_key(day[:7]), f"d:{day}:ds", str(sent)],
                ["EXPIRE", _daily_key(day[:7]), str(HISTORY_TTL_SECONDS)],
            ]
        )
    except Exception:  # noqa: BLE001
        logger.warning("Could not record the digest delivery.")


def build_summary(
    *,
    days: int = DEFAULT_DAYS,
    weeks: int = DEFAULT_WEEKS,
    months: int = DEFAULT_MONTHS,
    top_users: int = DEFAULT_TOP_USERS,
) -> dict[str, object]:
    """
    Builds the payload the Grafana dashboard renders.

    A payload younger than ``SUMMARY_TTL_SECONDS`` is served from the cache, so a dashboard
    that refreshes aggressively cannot drain the Upstash command quota.
    """
    cached = _cached_summary()
    if cached is not None:
        return cached

    snapshot = _fetch(days=days, weeks=weeks, months=months, top_users=top_users)
    payload: dict[str, object] = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "window": {"days": days, "weeks": weeks, "months": months},
        "totals": _totals_row(snapshot),
        "daily": _daily_rows(snapshot),
        "weekly": _weekly_rows(snapshot),
        "monthly": _monthly_rows(snapshot),
        "commands": _command_rows(snapshot),
        "hourly": _hourly_rows(snapshot),
        "digest": _digest_rows(snapshot),
        "users": snapshot.top_users,
    }
    _store_summary(payload)
    return payload


def _now() -> dt.datetime:
    """Returns the current time in the market timezone the bot reports in."""
    return dt.datetime.now(MARKET_TIMEZONE)


def _daily_key(month: str) -> str:
    return f"{PREFIX}:daily:{month}"


def _day_users_key(day: str) -> str:
    return f"{PREFIX}:users:day:{day}"


def _week_users_key(week: str) -> str:
    return f"{PREFIX}:users:week:{week}"


def _month_users_key(month: str) -> str:
    return f"{PREFIX}:users:month:{month}"


def _user_key(user_id: str) -> str:
    return f"{PREFIX}:user:{user_id}"


# --- write path -------------------------------------------------------------------------


def _event_commands(event: CommandEvent, now: dt.datetime) -> list[list[str]]:
    """Builds the Redis commands that fold one event into the aggregates."""
    day = now.date().isoformat()
    month = day[:7]
    iso_week = now.isocalendar()
    week = f"{iso_week.year}-W{iso_week.week:02d}"
    daily_key = _daily_key(month)

    commands: list[list[str]] = [
        ["XADD", EVENTS_KEY, "MAXLEN", "~", str(EVENTS_MAXLEN), "*", *_event_fields(event, now)],
        ["HINCRBY", daily_key, f"d:{day}:c", "1"],
        ["HINCRBY", daily_key, f"d:{day}:h:{now.hour:02d}", "1"],
        ["EXPIRE", daily_key, str(HISTORY_TTL_SECONDS)],
        ["HINCRBY", TOTALS_KEY, "commands", "1"],
        ["HINCRBY", TOTALS_KEY, f"{COMMAND_FIELD_PREFIX}{event.command}", "1"],
    ]
    if not event.ok:
        commands.append(["HINCRBY", TOTALS_KEY, "errors", "1"])
        commands.append(["HINCRBY", daily_key, f"d:{day}:e", "1"])
    if event.user_id is not None:
        commands.extend(_user_commands(event, day=day, month=month, week=week, now=now))
    return commands


def _event_fields(event: CommandEvent, now: dt.datetime) -> list[str]:
    """Renders the fields of the raw event appended to the stream."""
    return [
        "ts",
        str(int(now.timestamp())),
        "command",
        event.command,
        "chat_id",
        str(event.chat_id),
        "user_id",
        "" if event.user_id is None else str(event.user_id),
        "username",
        event.username or "",
        "ok",
        "1" if event.ok else "0",
    ]


def _user_commands(
    event: CommandEvent,
    *,
    day: str,
    month: str,
    week: str,
    now: dt.datetime,
) -> list[list[str]]:
    """Builds the Redis commands that record the activity of one user."""
    user_id = str(event.user_id)
    seen = str(int(now.timestamp()))
    day_key = _day_users_key(day)
    week_key = _week_users_key(week)
    month_key = _month_users_key(month)
    user_key = _user_key(user_id)
    return [
        ["SADD", day_key, user_id],
        ["EXPIRE", day_key, str(HISTORY_TTL_SECONDS)],
        ["SADD", week_key, user_id],
        ["EXPIRE", week_key, str(HISTORY_TTL_SECONDS)],
        ["SADD", month_key, user_id],
        ["EXPIRE", month_key, str(HISTORY_TTL_SECONDS)],
        ["SADD", ALL_USERS_KEY, user_id],
        ["ZINCRBY", USER_COMMANDS_KEY, "1", user_id],
        ["HSET", user_key, "username", event.username or "", "last_seen", seen],
        ["HSETNX", user_key, "first_seen", seen],
    ]


# --- read path --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Snapshot:
    """Everything the renderers need, read from Redis in one pipeline."""

    days: list[str]
    weeks: list[str]
    months: list[str]
    daily: dict[str, str]
    totals: dict[str, str]
    day_users: dict[str, int]
    week_users: dict[str, int]
    month_users: dict[str, int]
    total_users: int
    top_users: list[dict[str, object]]


def _fetch(*, days: int, weeks: int, months: int, top_users: int) -> _Snapshot:
    """Reads every aggregate the payload needs in two HTTP round trips."""
    today = _now().date()
    day_strings = _recent_days(today, days)
    week_strings = _recent_weeks(today, weeks)
    month_strings = _recent_months(today, months)
    daily_months = sorted({day[:7] for day in day_strings})

    replies = iter(redis_pipeline(_read_commands(daily_months, day_strings, week_strings, month_strings, top_users)))
    totals = _as_mapping(next(replies, None))
    daily = _merge_hashes(replies, daily_months)
    day_users = _scards(replies, day_strings)
    week_users = _scards(replies, week_strings)
    month_users = _scards(replies, month_strings)
    total_users = _as_int(next(replies, None))
    ranked = _as_list(next(replies, None))

    return _Snapshot(
        days=day_strings,
        weeks=week_strings,
        months=month_strings,
        daily=daily,
        totals=totals,
        day_users=day_users,
        week_users=week_users,
        month_users=month_users,
        total_users=total_users,
        top_users=_top_users(ranked),
    )


def _read_commands(
    daily_months: list[str],
    day_strings: list[str],
    week_strings: list[str],
    month_strings: list[str],
    top_users: int,
) -> list[list[str]]:
    """Builds the read pipeline; the replies are consumed in exactly this order."""
    commands: list[list[str]] = [
        ["HGETALL", TOTALS_KEY],
        *(["HGETALL", _daily_key(month)] for month in daily_months),
        *(["SCARD", _day_users_key(day)] for day in day_strings),
        *(["SCARD", _week_users_key(week)] for week in week_strings),
        *(["SCARD", _month_users_key(month)] for month in month_strings),
        ["SCARD", ALL_USERS_KEY],
        ["ZREVRANGE", USER_COMMANDS_KEY, "0", str(top_users - 1), "WITHSCORES"],
    ]
    return commands


def _merge_hashes(replies: Iterator[object], months: list[str]) -> dict[str, str]:
    """Merges the consecutive ``HGETALL`` replies of ``months`` into one mapping."""
    merged: dict[str, str] = {}
    for _ in months:
        merged.update(_as_mapping(next(replies, None)))
    return merged


def _top_users(ranked: list[object]) -> list[dict[str, object]]:
    """Reads the profiles of the ranked users and renders the top-user rows."""
    user_ids = [str(ranked[index]) for index in range(0, len(ranked), 2)]
    scores = {str(ranked[index]): _as_int(ranked[index + 1]) for index in range(0, len(ranked), 2)}
    profiles = _user_profiles(user_ids)
    return [_user_row(user_id, profiles.get(user_id, {}), scores.get(user_id, 0)) for user_id in user_ids]


def _user_profiles(user_ids: list[str]) -> dict[str, dict[str, str]]:
    """Reads the profile hash of every ranked user in one pipeline."""
    if not user_ids:
        return {}
    results = redis_pipeline([["HGETALL", _user_key(user_id)] for user_id in user_ids])
    return {user_id: _as_mapping(result) for user_id, result in zip(user_ids, results, strict=True)}


def _recent_days(today: dt.date, count: int) -> list[str]:
    """Returns the last ``count`` local dates, oldest first."""
    return [(today - dt.timedelta(days=offset)).isoformat() for offset in range(count - 1, -1, -1)]


def _recent_weeks(today: dt.date, count: int) -> list[str]:
    """Returns the last ``count`` ISO weeks, oldest first."""
    monday = today - dt.timedelta(days=today.weekday())
    return [_week_label(monday - dt.timedelta(weeks=offset)) for offset in range(count - 1, -1, -1)]


def _week_label(day: dt.date) -> str:
    """Formats a date as the ISO week it belongs to, ``YYYY-Www``."""
    iso_week = day.isocalendar()
    return f"{iso_week.year}-W{iso_week.week:02d}"


def _recent_months(today: dt.date, count: int) -> list[str]:
    """Returns the last ``count`` months, oldest first."""
    index = today.year * 12 + today.month - 1
    return [_month_label(index - offset) for offset in range(count - 1, -1, -1)]


def _month_label(index: int) -> str:
    """Formats a month index (``year * 12 + month - 1``) as ``YYYY-MM``."""
    year, month = divmod(index, 12)
    return f"{year:04d}-{month + 1:02d}"


def _totals_row(snapshot: _Snapshot) -> dict[str, int]:
    """Returns the all-time counters, as a single row."""
    return {
        "users": snapshot.total_users,
        "commands": _field_int(snapshot.totals, "commands"),
        "errors": _field_int(snapshot.totals, "errors"),
        "digest_sent": _field_int(snapshot.totals, "digest"),
    }


def _daily_rows(snapshot: _Snapshot) -> list[dict[str, object]]:
    """Returns one row per day for the requested window."""
    return [
        {
            "date": day,
            "time": _iso_midnight(day),
            "commands": _field_int(snapshot.daily, f"d:{day}:c"),
            "errors": _field_int(snapshot.daily, f"d:{day}:e"),
            "digest_sent": _field_int(snapshot.daily, f"d:{day}:ds"),
            "users": snapshot.day_users.get(day, 0),
        }
        for day in snapshot.days
    ]


def _weekly_rows(snapshot: _Snapshot) -> list[dict[str, object]]:
    """Returns one row per ISO week for the requested window."""
    return [
        {"week": week, "time": _iso_midnight(_week_start(week)), "users": snapshot.week_users.get(week, 0)}
        for week in snapshot.weeks
    ]


def _monthly_rows(snapshot: _Snapshot) -> list[dict[str, object]]:
    """Returns one row per month for the requested window."""
    return [
        {"month": month, "time": _iso_midnight(f"{month}-01"), "users": snapshot.month_users.get(month, 0)}
        for month in snapshot.months
    ]


def _command_rows(snapshot: _Snapshot) -> list[dict[str, object]]:
    """Returns the all-time usage of every command, most used first."""
    rows: list[dict[str, object]] = [
        {"command": field.removeprefix(COMMAND_FIELD_PREFIX), "count": _as_int(value)}
        for field, value in snapshot.totals.items()
        if field.startswith(COMMAND_FIELD_PREFIX)
    ]
    return sorted(rows, key=lambda row: _as_int(row["count"]), reverse=True)


def _hourly_rows(snapshot: _Snapshot) -> list[dict[str, int]]:
    """Returns the number of commands per hour of the day, summed over the window."""
    totals = [0] * HOURS_PER_DAY
    for day in snapshot.days:
        for hour in range(HOURS_PER_DAY):
            totals[hour] += _field_int(snapshot.daily, f"d:{day}:h:{hour:02d}")
    return [{"hour": hour, "count": totals[hour]} for hour in range(HOURS_PER_DAY)]


def _digest_rows(snapshot: _Snapshot) -> list[dict[str, object]]:
    """Returns how many digest messages were delivered per day."""
    return [
        {"date": day, "time": _iso_midnight(day), "sent": _field_int(snapshot.daily, f"d:{day}:ds")}
        for day in snapshot.days
    ]


def _week_start(week: str) -> str:
    """Returns the ISO date of the Monday that opens an ``YYYY-Www`` week."""
    year, _, number = week.partition("-W")
    return dt.date.fromisocalendar(int(year), int(number), 1).isoformat()


def _iso_midnight(day: str) -> str:
    """Returns the UTC midnight of a ``YYYY-MM-DD`` date, as Grafana expects ISO-8601."""
    return f"{day}T00:00:00Z"


def _user_row(user_id: str, profile: dict[str, str], commands: int) -> dict[str, object]:
    """Returns one row of the per-user activity table."""
    return {
        "user_id": _as_int(user_id),
        "username": profile.get("username", ""),
        "commands": commands,
        "first_seen": _iso_timestamp(profile.get("first_seen")),
        "last_seen": _iso_timestamp(profile.get("last_seen")),
    }


def _iso_timestamp(value: str | None) -> str:
    """Converts a stored epoch-second string into an ISO-8601 instant."""
    if not value or not value.isdigit():
        return ""
    return dt.datetime.fromtimestamp(int(value), tz=dt.UTC).isoformat()


# --- cache ------------------------------------------------------------------------------


def _cached_summary() -> dict[str, object] | None:
    """Returns the cached payload, or ``None`` when there is no usable entry."""
    raw = redis_command(["GET", SUMMARY_KEY])
    if not isinstance(raw, str) or not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Ignoring a corrupt analytics summary cache entry.")
        return None
    return payload if isinstance(payload, dict) else None


def _store_summary(payload: dict[str, object]) -> None:
    """Caches the payload for ``SUMMARY_TTL_SECONDS``. Never raises."""
    try:
        redis_pipeline([["SETEX", SUMMARY_KEY, str(SUMMARY_TTL_SECONDS), json.dumps(payload)]])
    except Exception:  # noqa: BLE001
        logger.warning("Could not cache the analytics summary.")


# --- parsing ----------------------------------------------------------------------------


def _as_int(value: object) -> int:
    """Coerces a Redis reply (int or numeric string) into an ``int``, defaulting to 0."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _as_list(value: object) -> list[object]:
    """Returns the reply as a list, defaulting to an empty one."""
    return value if isinstance(value, list) else []


def _as_mapping(value: object) -> dict[str, str]:
    """Returns a Redis hash reply as a ``str -> str`` mapping, defaulting to empty."""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _scards(replies: Iterator[object], keys: Sequence[str]) -> dict[str, int]:
    """Reads the consecutive ``SCARD`` replies of ``keys`` out of the pipeline reply."""
    return {key: _as_int(next(replies, None)) for key in keys}


def _field_int(mapping: dict[str, str], field: str) -> int:
    """Reads a numeric hash field, defaulting to 0 when it is missing."""
    return _as_int(mapping.get(field))
