import json
from datetime import datetime

import numpy as np

from trading_bot.cycle.decision_log import DecisionLog
from trading_bot.timeutil import ET

NOW = datetime(2026, 10, 8, 11, 0, tzinfo=ET)


def test_appends_one_json_object_per_line(tmp_path):
    log = DecisionLog(tmp_path / "safety-check-log.json", clock=lambda: NOW)
    log.record("entry_skipped", symbol="AAPL", reasons=["D1"])
    log.record("stop_moved", symbol="NVDA", new_stop=104.99)
    lines = log.path.read_text().splitlines()
    first, second = (json.loads(line) for line in lines)
    assert first["event"] == "entry_skipped" and first["symbol"] == "AAPL"
    assert first["timestamp"] == NOW.isoformat()
    assert second["new_stop"] == 104.99


def test_numpy_values_are_serialised_as_plain_python(tmp_path):
    log = DecisionLog(tmp_path / "log.json", clock=lambda: NOW)
    log.record("check", passed=np.bool_(True), price=np.float64(1.5), n=np.int64(3))
    row = json.loads(log.path.read_text())
    assert row["passed"] is True and row["price"] == 1.5 and row["n"] == 3


def test_log_is_appended_not_overwritten(tmp_path):
    path = tmp_path / "log.json"
    DecisionLog(path, clock=lambda: NOW).record("a")
    DecisionLog(path, clock=lambda: NOW).record("b")
    assert len(path.read_text().splitlines()) == 2
