import importlib.util

from loguru import logger

from zonneplan_telegram.api.hourly_prices import (
    get_zonneplan_hourly_prices,
)
from zonneplan_telegram.chart import generate_zonneplan_bar_chart
from zonneplan_telegram.storage import PriceStorage
from zonneplan_telegram.telegram import send_telegram_message, send_telegram_photo

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

    generate_zonneplan_bar_chart(response.prices, output_path="chart.png")
    send_telegram_photo(
        photo_path="chart.png",
        caption="Grafico dei prezzi orari di Zonneplan",
    )


if __name__ == "__main__":
    main()
