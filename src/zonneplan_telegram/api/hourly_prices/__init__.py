import datetime

import requests

from zonneplan_telegram.api import API_URL as _BASE_API_URL
from zonneplan_telegram.api.hourly_prices.model import APIResponse, PriceItem

API_URL = f"{_BASE_API_URL}/consumer-prices/charts/electricity-hourly"


def get_zonneplan_hourly_prices() -> APIResponse:
    url = API_URL
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    return APIResponse.from_raw_json(data)
