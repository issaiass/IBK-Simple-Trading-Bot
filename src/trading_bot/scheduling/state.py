"""What setup changed, so cleanup can undo it exactly."""
import json
from pathlib import Path

KEY = "original_standby_timeout_ac_minutes"
DEFAULT_STANDBY_MINUTES = 30  # Windows' usual default, used only if nothing was recorded


class ScheduleState:
    def __init__(self, path: Path):
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def original_standby(self) -> int | None:
        if not self.path.exists():
            return None
        try:
            return json.loads(self.path.read_text(encoding="utf-8")).get(KEY)
        except (ValueError, OSError):
            return None

    def record_original_standby(self, minutes: int) -> None:
        """Remember the value once. A re-run would read the keep-awake 0 instead."""
        if self.original_standby() is None:
            self.path.write_text(json.dumps({KEY: minutes}), encoding="utf-8")

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)
