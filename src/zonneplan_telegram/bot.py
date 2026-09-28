import os
from datetime import datetime

import requests

from zonneplan_telegram.api.hourly_prices import API_URL, get_zonneplan_hourly_prices



def main():
    msg = get_zonneplan_hourly_prices()
    send_telegram_message(msg)


if __name__ == "__main__":
    main()
