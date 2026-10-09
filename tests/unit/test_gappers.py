import pytest

from trading_bot.scanner.gappers import (
    Snapshot,
    from_yahoo,
    gap_pct,
    select_gappers,
    to_yahoo,
)


class TestSymbolMapping:
    @pytest.mark.parametrize("ibkr, yahoo", [("AAPL", "AAPL"), ("BRK B", "BRK-B"), ("BF B", "BF-B")])
    def test_round_trip(self, ibkr, yahoo):
        assert to_yahoo(ibkr) == yahoo
        assert from_yahoo(yahoo) == ibkr


class TestGapPct:
    def test_gap_up(self):
        assert gap_pct(prior_close=100.0, price=103.0) == pytest.approx(3.0)

    def test_gap_down_is_negative(self):
        assert gap_pct(100.0, 95.0) == pytest.approx(-5.0)

    def test_zero_prior_close_is_zero(self):
        assert gap_pct(0.0, 10.0) == 0.0


def snap(symbol, prior, price):
    return Snapshot(symbol, prior_close=prior, price=price)


class TestSelectGappers:
    def test_keeps_gaps_at_or_above_threshold(self):
        result = select_gappers(
            [snap("A", 100, 103), snap("B", 100, 102.9), snap("C", 100, 110)],
            min_gap_pct=3.0, min_price=3.0,
        )
        assert [g.symbol for g in result] == ["C", "A"]

    def test_sorted_by_gap_descending(self):
        result = select_gappers(
            [snap("A", 100, 104), snap("B", 100, 120), snap("C", 100, 108)],
            3.0, 3.0,
        )
        assert [g.symbol for g in result] == ["B", "C", "A"]

    def test_gap_downs_are_excluded(self):
        assert select_gappers([snap("A", 100, 90)], 3.0, 3.0) == []

    def test_min_price_filter(self):
        result = select_gappers([snap("PENNY", 2.0, 2.5), snap("OK", 10.0, 10.5)], 3.0, 3.0)
        assert [g.symbol for g in result] == ["OK"]

    def test_result_carries_gap_percentage(self):
        (g,) = select_gappers([snap("A", 100, 105)], 3.0, 3.0)
        assert g.gap_pct == pytest.approx(5.0) and g.price == 105

    def test_empty_input(self):
        assert select_gappers([], 3.0, 3.0) == []
