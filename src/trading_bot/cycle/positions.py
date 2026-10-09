"""Open-position state, persisted to open_positions.json."""
import json
from dataclasses import asdict, dataclass
from pathlib import Path

STATE_PRE_BREAKEVEN = "pre_breakeven"
STATE_BE_NO_PARTIAL = "post_breakeven_no_partial"
STATE_BE_PARTIAL = "post_breakeven_partial_done"


@dataclass
class Position:
    symbol: str
    entry_price: float
    entry_time_iso: str
    qty: float
    initial_stop: float
    stop_order_id: int
    state: str
    R: float
    stop_price: float | None = None  # the stop currently working at the broker

    def __post_init__(self):
        if self.stop_price is None:
            self.stop_price = self.initial_stop


class PositionStore:
    def __init__(self, path: Path):
        self.path = path

    def load(self) -> list[Position]:
        """Saved positions; [] if the file is missing. A corrupt file raises."""
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{self.path} is corrupt: {exc}") from exc
        return [Position(**row) for row in rows]

    def save(self, positions: list[Position]) -> None:
        """Atomic write: temp file, then replace."""
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(json.dumps([asdict(p) for p in positions], indent=2), encoding="utf-8")
        temp.replace(self.path)
