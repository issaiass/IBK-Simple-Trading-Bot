"""Load strategy rules and locate project paths."""
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RULES_PATH = PROJECT_ROOT / "config" / "rules.json"
LOG_DIR = PROJECT_ROOT / "logs"
SAFETY_LOG = LOG_DIR / "safety_log.jsonl"
TRADES_CSV = PROJECT_ROOT / "trades.csv"
WATCHLIST_PATH = PROJECT_ROOT / "watchlist.txt"
POSITIONS_PATH = PROJECT_ROOT / "open_positions.json"
DECISION_LOG_PATH = PROJECT_ROOT / "safety-check-log.json"
CYCLE_ERROR_LOG = LOG_DIR / "cycle_errors.log"
SCHEDULE_STATE_PATH = PROJECT_ROOT / "schedule_state.json"
CRONTAB_BACKUP_PATH = PROJECT_ROOT / "schedule_crontab.backup"


def venv_python_path(platform: str, root: Path) -> Path:
    """The venv interpreter. Deliberately not .resolve()d: that can jump to the base python."""
    if platform == "win32":
        return root / ".venv" / "Scripts" / "python.exe"
    return root / ".venv" / "bin" / "python"


VENV_PYTHON = venv_python_path(sys.platform, PROJECT_ROOT)


def load_rules(path: Path = RULES_PATH) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)
