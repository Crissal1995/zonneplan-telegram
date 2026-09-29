import importlib.util

from loguru import logger

from zonneplan_telegram.api.hourly_prices import (
    get_zonneplan_hourly_prices,
)
from zonneplan_telegram.storage import PriceStorage
from zonneplan_telegram.telegram import send_telegram_message

# Load environment variables from .env file if python-dotenv is installed
importlib.util.find_spec("dotenv") and importlib.import_module("dotenv").load_dotenv()


def main() -> None:
    response = get_zonneplan_hourly_prices()
    logger.info("Fetched Zonneplan hourly prices successfully.")
    logger.debug("Response data: {}", response)

    markdown_msg = response.as_markdown()
    logger.debug("Response as markdown: {}", markdown_msg)

    storage = PriceStorage()
    storage.save_prices(response.prices)

    send_telegram_message(markdown_msg)


if __name__ == "__main__":
    main()
