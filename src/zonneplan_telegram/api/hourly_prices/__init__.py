import requests

from zonneplan_telegram.api import API_URL as _BASE_API_URL
from zonneplan_telegram.api.hourly_prices.model import APIResponse

ELECTRICITY_HOURLY = f"{_BASE_API_URL}/consumer-prices/charts/electricity-hourly"
ELECTRICITY_QUARTER_HOURLY = f"{_BASE_API_URL}/consumer-prices/charts/electricity-quarter-hourly"


def get_zonneplan_hourly_prices() -> APIResponse:
    url = ELECTRICITY_HOURLY
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    return APIResponse.from_raw_json(data)


def get_zonneplan_quarter_hourly_prices() -> APIResponse:
    url = ELECTRICITY_QUARTER_HOURLY
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = response.json()
    return APIResponse.from_raw_json(data)
