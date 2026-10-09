from datetime import datetime, timedelta

import pytest

from trading_bot.reporting.performance import ClosedTrade
from trading_bot.reporting.rmultiple import (
    HISTOGRAM_LABELS,
    StopRecord,
    attach_r,
    histogram,
    r_multiple,
)
from trading_bot.timeutil import ET

OPENED = datetime(2026, 10, 8, 10, 0, tzinfo=ET)
CLOSED = OPENED + timedelta(hours=1)


def trade(symbol="NVDA", entry=100.0, exit_=102.0, stop=None, opened=OPENED):
    return ClosedTrade(
        symbol=symbol, qty=10, entry_price=entry, exit_price=exit_,
        pnl_usd=(exit_ - entry) * 10, pnl_pct=(exit_ - entry) / entry * 100,
        hold_minutes=60, opened=opened, closed=opened + timedelta(hours=1), stop_price=stop,
    )


def record(symbol="NVDA", stop=98.0, after_seconds=30, base=OPENED):
    return StopRecord(symbol, base + timedelta(seconds=after_seconds), stop)


class TestRMultiple:
    @pytest.mark.parametrize("entry, exit_, stop, expected", [
        (100, 102, 98, 1.0),
        (100, 96, 98, -2.0),
        (100, 100, 98, 0.0),
        (100, 106, 98, 3.0),
        (50, 51, 49.5, 2.0),
    ])
    def test_r_is_the_gain_in_units_of_initial_risk(self, entry, exit_, stop, expected):
        assert r_multiple(entry, exit_, stop) == pytest.approx(expected)

    @pytest.mark.parametrize("stop", [100, 101])
    def test_stop_at_or_above_entry_has_no_defined_risk(self, stop):
        assert r_multiple(100, 102, stop) is None


class TestAttachR:
    def test_stop_price_column_comes_first(self):
        (r,) = attach_r([trade(stop=98.0)], [record(stop=90.0)])
        assert (r.initial_stop, r.r_source) == (98.0, "trades_csv")
        assert r.r_multiple == pytest.approx(1.0)

    def test_decision_log_entry_is_next(self):
        (r,) = attach_r([trade()], [record(stop=98.0)])
        assert (r.initial_stop, r.r_source) == (98.0, "decision_log")
        assert r.r_multiple == pytest.approx(1.0)

    def test_proxy_of_one_percent_of_entry_is_the_last_resort(self):
        (r,) = attach_r([trade(entry=100.0, exit_=102.0)])
        assert (r.initial_stop, r.r_source) == (pytest.approx(99.0), "proxy")
        assert r.r_multiple == pytest.approx(2.0)

    def test_log_record_for_another_symbol_is_ignored(self):
        (r,) = attach_r([trade("NVDA")], [record("MU", stop=90.0)])
        assert r.r_source == "proxy"

    def test_log_record_before_the_entry_is_ignored(self):
        (r,) = attach_r([trade()], [record(after_seconds=-60)])
        assert r.r_source == "proxy"

    def test_log_record_long_after_the_entry_is_ignored(self):
        (r,) = attach_r([trade()], [record(after_seconds=11 * 60)])
        assert r.r_source == "proxy"

    def test_the_closest_following_record_wins(self):
        records = [record(stop=90.0, after_seconds=400), record(stop=98.0, after_seconds=20)]
        (r,) = attach_r([trade()], records)
        assert r.initial_stop == 98.0

    def test_each_trade_matches_its_own_record(self):
        later = OPENED + timedelta(hours=3)
        trades = [trade(), trade(opened=later, entry=200.0, exit_=204.0)]
        records = [record(stop=98.0), record(stop=196.0, base=later)]
        first, second = attach_r(trades, records)
        assert (first.initial_stop, second.initial_stop) == (98.0, 196.0)
        assert second.r_multiple == pytest.approx(1.0)

    def test_nonsense_stop_gives_no_r_but_keeps_the_trade(self):
        (r,) = attach_r([trade(stop=105.0)])
        assert r.r_multiple is None and r.trade.symbol == "NVDA"

    def test_empty(self):
        assert attach_r([]) == []


class TestHistogram:
    def test_seven_buckets_in_order(self):
        buckets = histogram([])
        assert [b.label for b in buckets] == HISTOGRAM_LABELS == [
            "≤ -2R", "-2R to -1R", "-1R to 0R", "0R to +1R", "+1R to +2R", "+2R to +3R", "> +3R",
        ]
        assert [b.count for b in buckets] == [0] * 7

    def test_open_ended_buckets_have_no_outer_bound(self):
        first, *_, last = histogram([])
        assert first.lower is None and first.upper == -2 and last.lower == 3 and last.upper is None

    @pytest.mark.parametrize("value, index", [
        (-5, 0), (-2, 0), (-1.99, 1), (-1, 1), (-0.5, 2), (0, 2),
        (0.01, 3), (1, 3), (1.5, 4), (2, 4), (2.5, 5), (3, 5), (3.01, 6), (10, 6),
    ])
    def test_bucket_edges_are_inclusive_on_the_upper_side(self, value, index):
        counts = [b.count for b in histogram([value])]
        assert counts[index] == 1 and sum(counts) == 1

    def test_counts_accumulate_and_none_is_skipped(self):
        counts = [b.count for b in histogram([-3, -2.5, 0.5, 0.7, 4, None])]
        assert counts == [2, 0, 0, 2, 0, 0, 1]
