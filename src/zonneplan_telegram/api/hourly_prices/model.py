import datetime
from typing import Any, Literal

from pydantic import BaseModel

PriceEntry = dict[Literal["amount"], float]


class PriceItem(BaseModel):
    start_date: datetime.datetime
    end_date: datetime.datetime
    price_tax_included: PriceEntry

    @property
    def price(self) -> float:
        return self.price_tax_included["amount"]


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
            message_lines.append(f"{start_time} - {end_time}: €{price:.2f}")
        return "\n".join(message_lines)
