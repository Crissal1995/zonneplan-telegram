import datetime
from typing import Any, Literal

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
