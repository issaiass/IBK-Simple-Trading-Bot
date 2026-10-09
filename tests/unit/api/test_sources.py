import json
from datetime import datetime, timedelta

from trading_bot.api.sources import CachedPriceProvider, DecisionLogReader
from trading_bot.timeutil import ET

T0 = datetime(2026, 10, 8, 11, 0, tzinfo=ET)


def write_log(path, events):
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")


def event(name, minutes=0, **fields):
    return {"timestamp": (T0 + timedelta(minutes=minutes)).isoformat(), "event": name, **fields}


class TestDecisionLogReader:
    def test_missing_file_has_no_events(self, tmp_path):
        reader = DecisionLogReader(tmp_path / "nope.json")
        assert reader.last_event() is None and reader.last_cycle() is None
        assert reader.entered_stops() == []

    def test_last_event_is_the_final_line(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("cycle"), event("entry_skipped", 1, symbol="MU")])
        assert DecisionLogReader(path).last_event()["event"] == "entry_skipped"

    def test_last_cycle_is_the_newest_heartbeat_even_with_later_events(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("cycle", 0), event("cycle", 5, status="ok"),
                         event("entry_skipped", 6, symbol="MU")])
        cycle = DecisionLogReader(path).last_cycle()
        assert cycle["timestamp"] == (T0 + timedelta(minutes=5)).isoformat()
        assert cycle["status"] == "ok"

    def test_no_heartbeat_means_no_last_cycle(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("entry_skipped", symbol="MU")])
        assert DecisionLogReader(path).last_cycle() is None

    def test_corrupt_and_blank_lines_are_skipped(self, tmp_path):
        path = tmp_path / "log.json"
        path.write_text(json.dumps(event("cycle")) + "\n{broken\n\n" + json.dumps(event("x")) + "\n",
                        encoding="utf-8")
        reader = DecisionLogReader(path)
        assert reader.last_event()["event"] == "x" and reader.last_cycle()["event"] == "cycle"

    def test_truncated_final_line_falls_back_to_the_previous_good_one(self, tmp_path):
        path = tmp_path / "log.json"
        path.write_text(json.dumps(event("cycle")) + '\n{"timestamp": "2026-10', encoding="utf-8")
        assert DecisionLogReader(path).last_event()["event"] == "cycle"

    def test_entered_events_become_stop_records(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("entered", 1, symbol="NVDA", stop=97.02, entry_price=100.1),
                         event("entry_skipped", 2, symbol="MU"),
                         event("entered", 3, symbol="BBY", stop=83.9)])
        records = DecisionLogReader(path).entered_stops()
        assert [(r.symbol, r.stop) for r in records] == [("NVDA", 97.02), ("BBY", 83.9)]
        assert records[0].time == T0 + timedelta(minutes=1)

    def test_entered_events_without_a_usable_stop_are_ignored(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("entered", symbol="X"), event("entered", symbol="Y", stop="n/a")])
        assert DecisionLogReader(path).entered_stops() == []

    def test_reflects_the_file_changing_between_calls(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("entered", symbol="A", stop=1.0)])
        reader = DecisionLogReader(path)
        assert len(reader.entered_stops()) == 1
        write_log(path, [event("entered", symbol="A", stop=1.0), event("entered", 1, symbol="B", stop=2.0)])
        assert len(reader.entered_stops()) == 2


class TestLastCycleEvents:
    def test_events_after_the_last_heartbeat_belong_to_that_cycle(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [
            event("cycle", 0, status="ok"), event("entered", 0, symbol="OLD"),
            event("cycle", 5, status="ok"), event("entry_skipped", 5, symbol="A"),
            event("entered", 5, symbol="B"),
        ])
        heartbeat, events = DecisionLogReader(path).last_cycle_events()
        assert heartbeat["timestamp"] == event("cycle", 5)["timestamp"]
        assert [e["event"] for e in events] == ["entry_skipped", "entered"]

    def test_a_cycle_with_nothing_after_it_has_no_events(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("cycle", 0, status="ok")])
        heartbeat, events = DecisionLogReader(path).last_cycle_events()
        assert heartbeat is not None and events == []

    def test_no_heartbeat_means_nothing(self, tmp_path):
        path = tmp_path / "log.json"
        write_log(path, [event("entered", 0, symbol="X")])
        assert DecisionLogReader(path).last_cycle_events() == (None, [])
        assert DecisionLogReader(tmp_path / "missing.json").last_cycle_events() == (None, [])


class TestCachedPriceProvider:
    def make(self, prices, ttl=15.0):
        self.now = 1000.0
        self.calls = []

        def fetch(symbol):
            self.calls.append(symbol)
            if symbol not in prices:
                raise ConnectionError("no data")
            return prices[symbol]

        return CachedPriceProvider(fetch, ttl_seconds=ttl, clock=lambda: self.now)

    def test_returns_prices_for_the_requested_symbols(self):
        provider = self.make({"NVDA": 235.5, "MU": 1070.0})
        assert provider.latest(["NVDA", "MU"]) == {"NVDA": 235.5, "MU": 1070.0}

    def test_failed_symbols_are_omitted_not_raised(self):
        provider = self.make({"NVDA": 235.5})
        assert provider.latest(["NVDA", "ZZZ"]) == {"NVDA": 235.5}

    def test_prices_are_cached_within_the_ttl(self):
        provider = self.make({"NVDA": 235.5})
        provider.latest(["NVDA"])
        self.now += 10
        provider.latest(["NVDA"])
        assert self.calls == ["NVDA"]

    def test_prices_are_refetched_after_the_ttl(self):
        provider = self.make({"NVDA": 235.5})
        provider.latest(["NVDA"])
        self.now += 16
        provider.latest(["NVDA"])
        assert self.calls == ["NVDA", "NVDA"]

    def test_failures_are_not_cached_so_the_next_poll_retries(self):
        provider = self.make({})
        provider.latest(["ZZZ"])
        provider.latest(["ZZZ"])
        assert self.calls == ["ZZZ", "ZZZ"]

    def test_no_symbols_means_no_fetches(self):
        provider = self.make({"NVDA": 1.0})
        assert provider.latest([]) == {} and self.calls == []
