"""CSV record of executed trades."""
import csv
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from trading_bot.timeutil import ET

HEADER = ["timestamp_iso", "symbol", "side", "size", "fill_price", "order_id", "status"]


class TradeLogLocked(Exception):
    """The CSV is held open by another process."""


class TradeLog:
    def __init__(self, path: Path, sleep: Callable[[float], None] = time.sleep):
        self.path = path
        self._sleep = sleep

    def ensure_header(self) -> None:
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(HEADER)

    def append(self, row: dict) -> None:
        """Append a row; retry once after 1s if the file is locked."""
        self.ensure_header()
        try:
            self._write_row(row)
        except PermissionError:
            self._sleep(1)
            try:
                self._write_row(row)
            except PermissionError as exc:
                raise TradeLogLocked(f"{self.path} is locked") from exc

    def last_row(self) -> dict | None:
        rows = self._read()
        return rows[-1] if rows else None

    def count_buys_on(self, day_et: date) -> int:
        """BUY rows whose UTC timestamp falls on `day_et` in Eastern time."""
        return sum(
            1
            for r in self._read()
            if r["side"] == "BUY"
            and datetime.fromisoformat(r["timestamp_iso"]).astimezone(ET).date() == day_et
        )

    def _write_row(self, row: dict) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=HEADER).writerow(row)

    def _read(self) -> list[dict]:
        self.ensure_header()
        with self.path.open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
