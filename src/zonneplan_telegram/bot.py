from loguru import logger

from zonneplan_telegram.api.hourly_prices import (
    get_zonneplan_hourly_prices,
    get_zonneplan_quarter_hourly_prices,
)
from zonneplan_telegram.telegram import send_telegram_message


def main() -> None:
    response = get_zonneplan_hourly_prices()
    logger.info("Fetched Zonneplan hourly prices successfully.")
    logger.debug("Response data: {}", response.as_markdown())
    send_telegram_message(response.as_markdown())

    response = get_zonneplan_quarter_hourly_prices()
    logger.info("Fetched Zonneplan quarter-hourly prices successfully.")
    logger.debug("Response data: {}", response.as_markdown())
    send_telegram_message(response.as_markdown())


if __name__ == "__main__":
    main()
