import json

import pytest

from trading_bot.cycle.positions import (
    STATE_PRE_BREAKEVEN,
    Position,
    PositionStore,
)


def make(symbol="NVDA", **kw):
    base = dict(
        symbol=symbol, entry_price=100.0, entry_time_iso="2026-10-08T14:00:00+00:00",
        qty=9, initial_stop=98.0, stop_order_id=7, state=STATE_PRE_BREAKEVEN, R=2.0,
    )
    return Position(**{**base, **kw})


def test_current_stop_defaults_to_initial_stop():
    assert make().stop_price == 98.0
    assert make(stop_price=100.0).stop_price == 100.0


def test_missing_file_loads_as_empty(tmp_path):
    assert PositionStore(tmp_path / "open_positions.json").load() == []


def test_round_trip(tmp_path):
    store = PositionStore(tmp_path / "open_positions.json")
    positions = [make("NVDA"), make("MU", qty=3, stop_price=101.5)]
    store.save(positions)
    assert store.load() == positions


def test_file_contains_the_documented_keys(tmp_path):
    store = PositionStore(tmp_path / "open_positions.json")
    store.save([make()])
    (row,) = json.loads(store.path.read_text())
    assert {"symbol", "entry_price", "entry_time_iso", "qty", "initial_stop",
            "stop_order_id", "state", "R"} <= set(row)


def test_save_is_atomic_and_leaves_no_temp_file(tmp_path):
    store = PositionStore(tmp_path / "open_positions.json")
    store.save([make("A")])
    store.save([make("B")])
    assert [p.symbol for p in store.load()] == ["B"]
    assert [f.name for f in tmp_path.iterdir()] == ["open_positions.json"]


def test_saving_empty_list_clears_positions(tmp_path):
    store = PositionStore(tmp_path / "open_positions.json")
    store.save([make()])
    store.save([])
    assert store.load() == []


def test_corrupt_file_raises_instead_of_silently_dropping_positions(tmp_path):
    path = tmp_path / "open_positions.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        PositionStore(path).load()
