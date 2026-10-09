"""Append-only decision log: one JSON object per line."""
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from trading_bot.timeutil import now_et


def _plain(value):
    """json default: numpy scalars (incl. numpy bool) and datetimes become plain Python."""
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, (set, tuple)):
        return list(value)
    return str(value)


class DecisionLog:
    def __init__(self, path: Path, clock: Callable[[], datetime] = now_et):
        self.path = path
        self._clock = clock

    def record(self, event: str, **fields) -> None:
        entry = {"timestamp": self._clock().isoformat(), "event": event, **fields}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=_plain) + "\n")
