from logging import getLogger

from zonneplan_telegram.api.hourly_prices import get_zonneplan_hourly_prices
from zonneplan_telegram.telegram import send_telegram_message

logger = getLogger(__name__)


def main() -> None:
    response = get_zonneplan_hourly_prices()
    logger.info("Fetched Zonneplan hourly prices successfully.")
    logger.debug("Response data: %s", response)
    send_telegram_message(response.as_markdown())


if __name__ == "__main__":
    main()
