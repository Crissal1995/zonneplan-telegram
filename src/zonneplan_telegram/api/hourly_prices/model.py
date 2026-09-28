import datetime
from collections import defaultdict
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel

PriceEntry = dict[Literal["amount"], float]


class PriceItem(BaseModel):
    start_date: datetime.datetime
    end_date: datetime.datetime
    price_tax_included: PriceEntry

    @property
    def price_eur(self) -> float:
        """
        Returns the price of the time span in EUR.
        """
        return self.price_tax_included["amount"] * 10e-8

    @property
    def price_cents(self) -> float:
        """
        Returns the price of the time span in cents.
        """
        return self.price_tax_included["amount"] * 10e-6


class APIResponse(BaseModel):
    prices: list[PriceItem]

    @classmethod
    def from_raw_json(cls, json_data: dict[str, Any]) -> "APIResponse":
        try:
            raw_prices = json_data["data"]["chart"]["series"]["prices"]
        except KeyError:
            msg = "Invalid JSON structure!"
            raise ValueError(msg) from None
        else:
            return cls(prices=[PriceItem.model_validate(item) for item in raw_prices])

    def as_markdown(self) -> str:
        class FormattedItem(NamedTuple):
            start_dt: datetime.datetime
            end_dt: datetime.datetime
            hour_range: str
            price: float

        # 1. Group and format items by day (YYYY-MM-DD)
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
        current_price = next(
            (
                item.price_cents
                for item in self.prices
                if item.start_date.astimezone()
                <= now_local
                < item.end_date.astimezone()
            ),
            None,
        )

        # Fallback to the closest available item if exact match fails
        if current_price is None and self.prices:
            current_price = self.prices[-1].price_cents

        # Build Message Header
        message_lines = [
            "⚡ **Zonneplan - Prezzi Energia** ⚡",
            f"💡 *Tariffa attuale:* `{current_price:.2f} ct/kWh`\n",
        ]

        # --- TODAY SECTION ---
        if today_items:
            t_min, t_max, t_avg = get_day_stats(today_items)
            message_lines.extend(
                [
                    f"📅 **Oggi ({today_key})**",
                    (
                        f"• Min: `{t_min:.2f} ct/kWh`\n"
                        f"• Max: `{t_max:.2f} ct/kWh`\n"
                        f"• Media: `{t_avg:.2f} ct/kWh`\n"
                    ),
                ]
            )
        else:
            message_lines.extend(
                [f"📅 **Oggi ({today_key})**", "• *Dati non disponibili*\n"]
            )

        # --- TOMORROW SECTION ---
        if tomorrow_items:
            tm_min, tm_max, tm_avg = get_day_stats(tomorrow_items)
            message_lines.extend(
                [
                    f"📅 **Domani ({tomorrow_key})**",
                    (
                        f"• Min: `{tm_min:.2f} ct/kWh`\n"
                        f"• Max: `{tm_max:.2f} ct/kWh`\n"
                        f"• Media: `{tm_avg:.2f} ct/kWh`\n"
                    ),
                ]
            )
        else:
            message_lines.extend(
                [
                    f"📅 **Domani ({tomorrow_key})**",
                    "• *Dati non disponibili*\n",
                ]
            )

        message_lines.append("_Made with ❤️ by Crissal1995_")
        return "\n".join(message_lines)
