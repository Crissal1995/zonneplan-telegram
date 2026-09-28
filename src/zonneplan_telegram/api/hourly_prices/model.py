import datetime
from typing import Any, Literal, NamedTuple

from pydantic import BaseModel

PriceEntry = dict[Literal["amount"], float]


class PriceItem(BaseModel):
    start_date: datetime.datetime
    end_date: datetime.datetime
    price_tax_included: PriceEntry

    @property
    def price(self) -> float:
        """
        Returns the price of the time span in EUR.
        """
        return self.price_tax_included["amount"] * 10e-8


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
        message_lines = ["*Zonneplan Hourly Prices:*"]
        for price_item in self.prices:
            start_time = price_item.start_date.strftime("%Y-%m-%d %H:%M")
            end_time = price_item.end_date.strftime("%Y-%m-%d %H:%M")
            price = price_item.price
            message_lines.append(f"{start_time} - {end_time}: €{price}")
        return "\n".join(message_lines)

    def format_telegram_message(self) -> str:
        class FormattedItem(NamedTuple):
            hour_range: str
            price: float

        formatted_items: list[FormattedItem] = []

        for item in self.prices:
            start = item.start_date
            end = item.end_date
            price = item.price_tax_included["amount"] * 10e-8

            formatted_items.append(
                FormattedItem(
                    hour_range=f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}",
                    price=price,
                )
            )

        # Find min, max and avg
        prices_only = [x.price for x in formatted_items]
        min_price = min(prices_only)
        max_price = max(prices_only)
        avg_price = sum(prices_only) / len(prices_only)

        # Find the price of the current hour
        current_price = next(
            (
                x.price
                for x in formatted_items
                if datetime.datetime.now().astimezone().hour
                == datetime.datetime.strptime(x.hour_range.split(" - ")[0], "%H:%M")
                .astimezone()
                .hour
            ),
            prices_only[0],
        )

        return (
            "⚡ ## Zonneplan - Prezzi Energia ⚡\n\n"
            f"💡 *Tariffa attuale:* `{current_price:.2f} €/kWh`\n\n"
            "📊 ## Riepilogo Giornaliero:\n"
            f"• 📉 **Minimo:** `{min_price:.2f} €/kWh`\n"
            f"• 📈 **Massimo:** `{max_price:.2f} €/kWh`\n"
            f"• ⚖️ **Media:** `{avg_price:.2f} €/kWh`\n\n"
            "_Made with ❤️ by Crissal1995_"
        )
