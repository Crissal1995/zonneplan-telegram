from zonneplan_telegram.api.hourly_prices import get_zonneplan_hourly_prices
from zonneplan_telegram.telegram import send_telegram_message


def main() -> None:
    response = get_zonneplan_hourly_prices()
    send_telegram_message(response.as_markdown())


if __name__ == "__main__":
    main()
