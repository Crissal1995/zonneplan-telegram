import json
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, RootModel

from zonneplan_telegram.api.hourly_prices.model import Prices

DEFAULT_STORAGE_PATH = Path("data/history.json")


class HistoryEntry(BaseModel):
    start_date: str
    end_date: str
    amount: float


class History(RootModel):
    root: dict[str, HistoryEntry]


class PriceStorage:
    def __init__(self, storage_path: str | Path = DEFAULT_STORAGE_PATH) -> None:
        self.storage_path = Path(storage_path)
        # Ensure the parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load_history(self) -> History:
        """Carica lo storico esistente dal file JSON."""
        if not self.storage_path.exists():
            return History.model_validate({})
        try:
            return History.model_validate(json.load(self.storage_path.open(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as error:
            logger.error(f"Error while loading the JSON at '{self.storage_path}'. Returning empty history.")
            logger.warning(f"Error details: {error}", exc_info=True)
            return History.model_validate({})

    def save_prices(self, prices: Prices) -> None:
        """Store the given list of Price objects into the JSON file, updating existing entries."""
        history = self.load_history()
        history_dict = history.model_dump()

        for item in prices:
            key = item.start_date.isoformat()
            history_dict[key] = {
                "start_date": item.start_date.isoformat(),
                "end_date": item.end_date.isoformat(),
                "amount": item.price_tax_included["amount"],
            }

        # Write the updated history back to the JSON file
        self.storage_path.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
