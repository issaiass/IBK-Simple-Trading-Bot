import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from trading_bot.strategy import evaluate
from trading_bot.timeutil import ET

RULES = {"time_filter": {"earliest_entry_et": "10:05", "latest_entry_et": "15:30"}}


def at(hour, minute):
    return datetime(2026, 10, 8, hour, minute, tzinfo=ET)


def position(symbol, qty):
    return SimpleNamespace(contract=SimpleNamespace(symbol=symbol), position=qty)


class FakeIB:
    def __init__(self, positions=()):
        self._positions = list(positions)

    def positions(self):
        return self._positions


class PriceSpy:
    def __init__(self, price=123.45):
        self.price, self.calls = price, 0

    def __call__(self, ib, symbol):
        self.calls += 1
        return self.price


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "logs" / "safety_log.jsonl"


def run(ib=None, now=at(11, 0), price_fn=None, log_path=None, symbol="NVDA"):
    return evaluate(
        symbol, ib or FakeIB(), rules=RULES, now=now,
        price_fn=price_fn or PriceSpy(), log_path=log_path,
    )


def test_passes_inside_window_without_position(log_path):
    result = run(log_path=log_path)
    assert result == {
        "pass": True,
        "reasons": ["time gate ok", "no existing position"],
        "price": 123.45,
    }


def test_already_in_position_fails(log_path):
    result = run(FakeIB([position("NVDA", 10)]), log_path=log_path)
    assert result == {"pass": False, "reasons": ["already in position"], "price": 0.0}


def test_other_symbol_or_short_position_does_not_block(log_path):
    ib = FakeIB([position("MU", 10), position("NVDA", -5), position("NVDA", 0)])
    assert run(ib, log_path=log_path)["pass"] is True


@pytest.mark.parametrize("now", [at(9, 30), at(10, 4), at(15, 31), at(18, 0)])
def test_outside_window_fails(now, log_path):
    result = run(now=now, log_path=log_path)
    assert result == {
        "pass": False,
        "reasons": ["outside entry window 10:05-15:30"],
        "price": 0.0,
    }


@pytest.mark.parametrize("now", [at(10, 5), at(15, 30)])
def test_window_edges_are_inclusive(now, log_path):
    assert run(now=now, log_path=log_path)["pass"] is True


def test_position_check_comes_before_time_gate(log_path):
    result = run(FakeIB([position("NVDA", 1)]), now=at(8, 0), log_path=log_path)
    assert result["reasons"] == ["already in position"]


def test_price_is_not_fetched_when_a_check_fails(log_path):
    spy = PriceSpy()
    run(FakeIB([position("NVDA", 1)]), price_fn=spy, log_path=log_path)
    run(now=at(8, 0), price_fn=spy, log_path=log_path)
    assert spy.calls == 0


def test_result_values_are_plain_python_types(log_path):
    result = run(log_path=log_path)
    assert type(result["pass"]) is bool and type(result["price"]) is float


def test_every_evaluation_is_appended_as_a_json_line(log_path):
    run(log_path=log_path)
    run(now=at(8, 0), log_path=log_path)
    lines = log_path.read_text().splitlines()
    assert len(lines) == 2  # directory was created automatically
    first, second = (json.loads(line) for line in lines)
    assert first["pass"] is True and first["symbol"] == "NVDA"
    assert second["pass"] is False and "timestamp" in second
