import datetime
from typing import Any

from pydantic import BaseModel


class PriceItem(BaseModel):
    start_date: datetime.datetime
    end_date: datetime.datetime
    price_tax_included: float


class APIResponse(BaseModel):
    prices: list[PriceItem]

    @classmethod
    def from_raw_json(cls, json_data: dict[str, Any]) -> "APIResponse":
        try:
            raw_prices = json_data["data"]["chart"]["series"]["prices"]
        except KeyError:
            raise ValueError("Invalid JSON structure!")
        else:
            return cls(prices=[PriceItem.model_validate(item) for item in raw_prices])
