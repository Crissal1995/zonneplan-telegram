import datetime as dt
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel

# Zonneplan publishes the Dutch day-ahead prices, so every "local" conversion resolves in the
# market timezone instead of the host timezone: Vercel runs in UTC, which used to shift the
# chart hours and the day boundaries by the DST offset.
MARKET_TIMEZONE = ZoneInfo("Europe/Amsterdam")

PriceEntry = dict[Literal["amount"], float]

# Number of consecutive hours considered when looking for the cheapest charging window.
DIGEST_WINDOW_HOURS = 5


def _now() -> dt.datetime:
    """Returns the current instant in the price market timezone."""
    return dt.datetime.now(MARKET_TIMEZONE)


class Price(BaseModel):
    start_date: dt.datetime
    end_date: dt.datetime
    price_tax_included: PriceEntry

    @property
    def price_eur(self) -> float:
        """
        Returns the price of the time span in EUR, e.g. 0.3012 EUR/kWh.
        """
        return self.price_tax_included["amount"] * 10e-8

    @property
    def price_cents(self) -> float:
        """
        Returns the price of the time span in EUR cents, e.g. 30.12 ct/kWh.
        """
        return self.price_tax_included["amount"] * 10e-6


Prices = list[Price]


class APIResponse(BaseModel):
    prices: Prices

    @classmethod
    def from_raw_json(cls, json_data: dict[str, Any]) -> "APIResponse":
        try:
            raw_prices = json_data["data"]["chart"]["series"]["prices"]
        except KeyError:
            msg = "Invalid JSON structure!"
            raise ValueError(msg) from None
        else:
            return cls(prices=[Price.model_validate(item) for item in raw_prices])

    def get_current_price(self) -> Price | None:
        """
        Returns the current price in EUR cents, or None if no price is available.
        """
        now = _now()
        for item in self.prices:
            if item.start_date.astimezone(MARKET_TIMEZONE) <= now < item.end_date.astimezone(MARKET_TIMEZONE):
                return item
        return None

    def get_today_prices(self) -> Prices:
        """
        Returns a list of Price objects for today, or an empty list if no prices are available.
        """
        today = _now().date()
        return [item for item in self.prices if item.start_date.astimezone(MARKET_TIMEZONE).date() == today]

    def get_tomorrow_prices(self) -> Prices:
        """
        Returns a list of Price objects for tomorrow, or an empty list if no prices are available.
        """
        tomorrow = (_now() + dt.timedelta(days=1)).date()
        return [item for item in self.prices if item.start_date.astimezone(MARKET_TIMEZONE).date() == tomorrow]

    def get_cheapest_window(self, hours: int) -> Prices | None:
        """
        Returns the ``hours`` consecutive slots of today with the lowest total price.

        Returns ``None`` when today's published prices cover fewer slots than requested. Ties
        resolve to the earliest window, because ``min`` keeps the first minimum it finds.
        """
        today_prices = sorted(self.get_today_prices(), key=lambda item: item.start_date)
        if len(today_prices) < hours:
            return None
        windows = (today_prices[index : index + hours] for index in range(len(today_prices) - hours + 1))
        return min(windows, key=lambda window: sum(item.price_cents for item in window))

    def as_price_now_markdown(self) -> str:
        """
        Renders the tariff of the current hour together with today's summary.
        """
        current_price = self.get_current_price()
        if current_price is None:
            return "⚡ **Zonneplan - Energy Prices** ⚡\n\n• *Current price not available.*"

        now_local = _now()
        start_local = current_price.start_date.astimezone(MARKET_TIMEZONE)
        end_local = current_price.end_date.astimezone(MARKET_TIMEZONE)

        message_lines = [
            "⚡ **Zonneplan - Current price** ⚡",
            "",
            f"💡 *Now:* `{current_price.price_cents:.2f} ct/kWh`",
            f"🕒 *Slot:* `{start_local:%H:%M} - {end_local:%H:%M}`",
        ]

        today_prices = self.get_today_prices()
        if today_prices:
            prices = [item.price_cents for item in today_prices]
            message_lines.extend(
                [
                    "",
                    f"📅 **Today ({now_local:%Y-%m-%d})**",
                    (
                        f"• Min: `{min(prices):.2f} ct/kWh`\n• Max: `{max(prices):.2f} ct/kWh`\n"
                        f"• Avg: `{sum(prices) / len(prices):.2f} ct/kWh`"
                    ),
                ]
            )

        return "\n".join(message_lines)

    def as_tomorrow_markdown(self) -> str:
        """
        Renders tomorrow's summary, or a notice when the prices are not published yet.
        """
        tomorrow_prices = self.get_tomorrow_prices()
        tomorrow_local = _now() + dt.timedelta(days=1)

        message_lines = [
            "⚡ **Zonneplan - Tomorrow's prices** ⚡",
            "",
            f"📅 **Tomorrow ({tomorrow_local:%Y-%m-%d})**",
        ]

        if not tomorrow_prices:
            message_lines.append("• *Prices not published yet.*")
            return "\n".join(message_lines)

        prices = [item.price_cents for item in tomorrow_prices]
        cheapest = min(tomorrow_prices, key=lambda item: item.price_cents)
        most_expensive = max(tomorrow_prices, key=lambda item: item.price_cents)

        message_lines.extend(
            [
                f"• Min: `{min(prices):.2f} ct/kWh` (`{cheapest.start_date.astimezone(MARKET_TIMEZONE):%H:%M}`)",
                f"• Max: `{max(prices):.2f} ct/kWh` (`{most_expensive.start_date.astimezone(MARKET_TIMEZONE):%H:%M}`)",
                f"• Avg: `{sum(prices) / len(prices):.2f} ct/kWh`",
            ]
        )

        return "\n".join(message_lines)

    def as_daily_digest_markdown(self) -> str:
        """
        Renders the daily digest: today's cheapest hour and the cheapest contiguous window.
        """
        now_local = _now()
        message_lines = [
            "⚡ **Zonneplan - Daily digest** ⚡",
            "",
            f"📅 **Today ({now_local:%Y-%m-%d})**",
        ]

        today_prices = self.get_today_prices()
        if not today_prices:
            message_lines.append("• *Prices not published yet.*")
            return "\n".join(message_lines)

        cheapest = min(today_prices, key=lambda item: item.price_cents)
        cheapest_hour = cheapest.start_date.astimezone(MARKET_TIMEZONE)
        message_lines.append(f"💡 Minimum: `{cheapest.price_cents:.2f} ct/kWh` at `{cheapest_hour:%H:%M}`")

        window = self.get_cheapest_window(DIGEST_WINDOW_HOURS)
        if window is None:
            message_lines.append(f"🏆 Cheapest {DIGEST_WINDOW_HOURS}h window: *not enough hours published yet.*")
            return "\n".join(message_lines)

        window_start = window[0].start_date.astimezone(MARKET_TIMEZONE)
        window_end = window[-1].end_date.astimezone(MARKET_TIMEZONE)
        window_average = sum(item.price_cents for item in window) / len(window)
        message_lines.append(
            f"🏆 Cheapest {DIGEST_WINDOW_HOURS}h window: `{window_start:%H:%M} - {window_end:%H:%M}` "
            f"(`avg {window_average:.2f} ct/kWh`)"
        )

        return "\n".join(message_lines)
