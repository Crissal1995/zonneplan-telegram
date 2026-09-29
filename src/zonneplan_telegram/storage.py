import json
from pathlib import Path

from loguru import logger
from pydantic import BaseModel, RootModel

from zonneplan_telegram.api.hourly_prices.model import Prices

DEFAULT_STORAGE_DIR = Path("data")


class HistoryEntry(BaseModel):
    start_date: str
    end_date: str
    amount: float


class DayHistory(RootModel):
    root: dict[str, HistoryEntry]

    @property
    def entries(self) -> list[HistoryEntry]:
        return list(self.root.values())


class PriceStorage:
    def __init__(self, storage_dir: str | Path = DEFAULT_STORAGE_DIR) -> None:
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, date_str: str) -> Path:
        """Restituisce il percorso del file per una specifica data (es. data/2026-09-29.json)"""
        return self.storage_dir / f"{date_str}.json"

    def load_day(self, date_str: str) -> DayHistory | None:
        """Carica lo storico di una specifica giornata."""
        file_path = self._get_file_path(date_str)
        if not file_path.exists():
            return None
        try:
            return DayHistory.model_validate(json.load(file_path.open(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as error:
            logger.error(f"Error while loading JSON at '{file_path}'. Returning empty history.")
            logger.warning(f"Error details: {error}", exc_info=True)
            return None

    def save_prices(self, prices: Prices) -> None:
        """
        Split the prices by day and save/update a separate JSON file for each day.
        Skips existing entries to avoid overwriting them.
        """
        # Raggruppa i prezzi per data locale (YYYY-MM-DD)
        prices_by_day: dict[str, Prices] = {}
        for item in prices:
            day_str = item.start_date.astimezone().strftime("%Y-%m-%d")
            prices_by_day.setdefault(day_str, []).append(item)

        # Salva ogni giorno nel suo file dedicato
        for day_str, day_prices in prices_by_day.items():
            file_path = self._get_file_path(day_str)
            original_day_history = self.load_day(day_str)
            new_day_history = DayHistory(root={})

            for item in day_prices:
                key = item.start_date.isoformat()
                new_day_history.root[key] = HistoryEntry(
                    start_date=item.start_date.isoformat(),
                    end_date=item.end_date.isoformat(),
                    amount=item.price_tax_included["amount"],
                )

            update = False
            if original_day_history:
                logger.info(f"File for {day_str} already exists.")
                if len(new_day_history.entries) > len(original_day_history.entries):
                    logger.info(f"More entries found for {day_str}. Updating history.")
                    update = True
            else:
                logger.info(f"Saving new history for {day_str}.")
                update = True

            if update:
                file_path.write_text(new_day_history.model_dump_json(indent=2), encoding="utf-8")
                logger.info(f"Saved history for {day_str} at {file_path}")
