import importlib.util

from loguru import logger

from zonneplan_telegram.api.hourly_prices import (
    get_zonneplan_hourly_prices,
)
from zonneplan_telegram.storage import PriceStorage

# Load environment variables from .env file if python-dotenv is installed
importlib.util.find_spec("dotenv") and importlib.import_module("dotenv").load_dotenv()


def update_prices() -> None:
    response = get_zonneplan_hourly_prices()
    logger.info("Fetched Zonneplan hourly prices successfully.")
    logger.debug("Response data: {}", response)
    storage = PriceStorage()
    storage.save_prices(response.prices)


if __name__ == "__main__":
    update_prices()
