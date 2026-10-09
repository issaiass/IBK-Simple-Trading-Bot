from datetime import datetime

import pytest

from trading_bot.scanner.gappers import Gapper, Snapshot
from trading_bot.scanner.service import run_scan, scan_loop
from trading_bot.scanner.watchlist import read_watchlist, write_watchlist
from trading_bot.timeutil import ET

RULES = {
    "universe_filters": {"min_price_usd": 3.0},
    "daily_filters": {"D3_min_gap_pct_from_prior_close": 3.0},
}
NOW = datetime(2026, 10, 8, 9, 0, tzinfo=ET)


def gapper(symbol, gap=5.0):
    return Gapper(symbol, prior_close=100.0, price=100 + gap, gap_pct=gap)


class TestWatchlistFile:
    def test_writes_one_symbol_per_line(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        write_watchlist(path, [gapper("NVDA"), gapper("BRK B")])
        assert path.read_text().splitlines() == ["NVDA", "BRK B"]

    def test_round_trip(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        write_watchlist(path, [gapper("AAA"), gapper("BBB")])
        assert read_watchlist(path) == ["AAA", "BBB"]

    def test_empty_scan_writes_empty_file(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        write_watchlist(path, [])
        assert read_watchlist(path) == []

    def test_missing_file_reads_as_empty(self, tmp_path):
        assert read_watchlist(tmp_path / "nope.txt") == []

    def test_write_replaces_previous_contents(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        write_watchlist(path, [gapper("OLD")])
        write_watchlist(path, [gapper("NEW")])
        assert read_watchlist(path) == ["NEW"]


class TestRunScan:
    def provider(self, snaps):
        calls = []

        def fetch(symbols, today):
            calls.append((list(symbols), today))
            return snaps

        fetch.calls = calls
        return fetch

    def test_filters_with_thresholds_from_rules_and_writes_watchlist(self, tmp_path):
        fetch = self.provider([
            Snapshot("UP", 100, 106), Snapshot("FLAT", 100, 101),
            Snapshot("PENNY", 2.0, 2.5),
        ])
        path = tmp_path / "watchlist.txt"
        result = run_scan(["UP", "FLAT", "PENNY"], RULES, fetch, path, clock=lambda: NOW)
        assert [g.symbol for g in result] == ["UP"]
        assert read_watchlist(path) == ["UP"]

    def test_passes_universe_and_todays_et_date_to_provider(self, tmp_path):
        fetch = self.provider([])
        run_scan(["AAA", "BBB"], RULES, fetch, tmp_path / "w.txt", clock=lambda: NOW)
        assert fetch.calls == [(["AAA", "BBB"], NOW.date())]

    def test_provider_failure_keeps_previous_watchlist(self, tmp_path):
        path = tmp_path / "watchlist.txt"
        write_watchlist(path, [gapper("KEEP")])

        def boom(symbols, today):
            raise ConnectionError("yahoo down")

        with pytest.raises(ConnectionError):
            run_scan(["AAA"], RULES, boom, path, clock=lambda: NOW)
        assert read_watchlist(path) == ["KEEP"]


class TestScanLoop:
    def test_scans_repeatedly_with_interval_between(self):
        events = []
        scan_loop(
            lambda: events.append("scan"),
            interval_seconds=1800,
            sleep=lambda s: events.append(("sleep", s)),
            iterations=3,
        )
        assert events == ["scan", ("sleep", 1800), "scan", ("sleep", 1800), "scan"]

    def test_a_failed_scan_does_not_stop_the_loop(self):
        calls = {"n": 0}
        errors = []

        def flaky():
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("yahoo down")

        scan_loop(flaky, 60, sleep=lambda s: None, iterations=2, on_error=errors.append)
        assert calls["n"] == 2 and len(errors) == 1
