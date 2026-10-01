import datetime
from collections import defaultdict
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel

PriceEntry = dict[Literal["amount"], float]


class Price(BaseModel):
    start_date: datetime.datetime
    end_date: datetime.datetime
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
        now = datetime.datetime.now().astimezone()
        for item in self.prices:
            if item.start_date.astimezone() <= now < item.end_date.astimezone():
                return item
        return None

    def get_today_prices(self) -> Prices:
        """
        Returns a list of Price objects for today, or an empty list if no prices are available.
        """
        now = datetime.datetime.now().astimezone()
        return [item for item in self.prices if item.start_date.astimezone().date() == now.date()]

    def get_tomorrow_prices(self) -> Prices:
        """
        Returns a list of Price objects for tomorrow, or an empty list if no prices are available.
        """
        now = datetime.datetime.now().astimezone()
        tomorrow = now + datetime.timedelta(days=1)
        return [item for item in self.prices if item.start_date.astimezone().date() == tomorrow.date()]

    def as_markdown(self) -> str:
        class FormattedItem(NamedTuple):
            start_dt: datetime.datetime
            end_dt: datetime.datetime
            hour_range: str
            price: float

        # Group and format items by day (YYYY-MM-DD)
        days_dict: dict[str, list[FormattedItem]] = defaultdict(list)

        for item in self.prices:
            start = item.start_date
            end = item.end_date
            price = item.price_cents

            day_key = start.strftime("%Y-%m-%d")
            days_dict[day_key].append(
                FormattedItem(
                    start_dt=start,
                    end_dt=end,
                    hour_range=f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}",
                    price=price,
                )
            )

        # Identify Today and Tomorrow based on local timezone
        now_local = datetime.datetime.now().astimezone()
        today_key = now_local.strftime("%Y-%m-%d")
        tomorrow_key = (now_local + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

        today_items = days_dict.get(today_key, [])
        tomorrow_items = days_dict.get(tomorrow_key, [])

        # Helper function to compute stats for a day
        def get_day_stats(items: list[FormattedItem]) -> tuple[float, float, float]:
            prices = [x.price for x in items]
            return min(prices), max(prices), sum(prices) / len(prices)

        # Find current price based on active hour interval (local time comparison)
        current_price = self.get_current_price()

        # Fallback to the closest available item if exact match fails
        if current_price is None and self.prices:
            current_price = self.prices[-1]

        if current_price is None:
            return "⚡ **Zonneplan - Energy Prices** ⚡\n\n• *Data not available*"

        # Build Message Header
        message_lines = [
            "⚡ **Zonneplan - Energy Prices** ⚡",
            f"💡 *Current rate:* `{current_price.price_cents:.2f} ct/kWh`\n",
        ]

        # --- TODAY SECTION ---
        if today_items:
            t_min, t_max, t_avg = get_day_stats(today_items)
            message_lines.extend(
                [
                    f"📅 **Today ({today_key})**",
                    (f"• Min: `{t_min:.2f} ct/kWh`\n• Max: `{t_max:.2f} ct/kWh`\n• Avg: `{t_avg:.2f} ct/kWh`\n"),
                ]
            )
        else:
            message_lines.extend([f"📅 **Today ({today_key})**", "• *Data not available*\n"])

        # --- TOMORROW SECTION ---
        if tomorrow_items:
            tm_min, tm_max, tm_avg = get_day_stats(tomorrow_items)
            message_lines.extend(
                [
                    f"📅 **Tomorrow ({tomorrow_key})**",
                    (f"• Min: `{tm_min:.2f} ct/kWh`\n• Max: `{tm_max:.2f} ct/kWh`\n• Avg: `{tm_avg:.2f} ct/kWh`\n"),
                ]
            )
        else:
            message_lines.extend(
                [
                    f"📅 **Tomorrow ({tomorrow_key})**",
                    "• *Data not available*\n",
                ]
            )

        message_lines.append("_Made with ❤️ by Crissal1995_")
        return "\n".join(message_lines)

    def as_price_now_markdown(self) -> str:
        """
        Renders the tariff of the current hour together with today's summary.
        """
        current_price = self.get_current_price()
        if current_price is None:
            return "⚡ **Zonneplan - Energy Prices** ⚡\n\n• *Current price not available.*"

        now_local = datetime.datetime.now().astimezone()
        start_local = current_price.start_date.astimezone()
        end_local = current_price.end_date.astimezone()

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
        tomorrow_local = datetime.datetime.now().astimezone() + datetime.timedelta(days=1)

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
                f"• Min: `{min(prices):.2f} ct/kWh` (`{cheapest.start_date.astimezone():%H:%M}`)",
                f"• Max: `{max(prices):.2f} ct/kWh` (`{most_expensive.start_date.astimezone():%H:%M}`)",
                f"• Avg: `{sum(prices) / len(prices):.2f} ct/kWh`",
            ]
        )

        return "\n".join(message_lines)
