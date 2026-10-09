import pandas as pd
import pytest

from tests.unit.test_cycle_filters import RULES, daily_frame, intraday_frame, run
from trading_bot.cycle import indicators
from trading_bot.cycle.indicators import (
    UnknownIndicator,
    compare,
    get_indicator,
    indicator,
    macd_hist,
    rsi,
)


def series(values):
    return pd.Series(values, dtype=float)


class TestRsi:
    def test_a_steady_rise_is_fully_overbought(self):
        assert rsi(series(range(1, 30)), period=14) == 100.0

    def test_a_steady_fall_is_fully_oversold(self):
        assert rsi(series(range(30, 1, -1)), period=14) == 0.0

    def test_a_choppy_market_sits_in_the_middle(self):
        choppy = series([10, 11] * 20)
        assert 40 < rsi(choppy, period=14) < 60

    def test_needs_more_bars_than_the_period(self):
        assert rsi(series(range(1, 15)), period=14) is None  # 14 bars give 13 changes
        assert rsi(series(range(1, 16)), period=14) is not None

    def test_period_defaults_to_14(self):
        assert rsi(series(range(1, 30))) == rsi(series(range(1, 30)), period=14)


class TestMacdHist:
    def test_an_accelerating_rise_is_positive(self):
        assert macd_hist(series([x * x for x in range(1, 60)])) > 0

    def test_an_accelerating_fall_is_negative(self):
        assert macd_hist(series([-x * x for x in range(1, 60)])) < 0

    def test_needs_slow_plus_signal_bars(self):
        assert macd_hist(series(range(1, 34))) is None  # 26 + 9 - 1 = 34 bars needed
        assert macd_hist(series(range(1, 35))) is not None

    def test_periods_are_adjustable(self):
        fast = macd_hist(series([x * x for x in range(1, 40)]), fast=3, slow=6, signal=3)
        assert fast is not None and fast > 0


class TestRegistry:
    def test_built_ins_are_registered(self):
        assert get_indicator("rsi") is rsi
        assert get_indicator("macd_hist") is macd_hist

    def test_unknown_names_are_rejected_with_the_choices(self):
        with pytest.raises(UnknownIndicator, match="rsi"):
            get_indicator("stochastic")

    def test_a_new_indicator_needs_only_a_decorated_function(self):
        @indicator("last_close")
        def last_close(close, **_):
            return float(close.iloc[-1])

        try:
            assert get_indicator("last_close")(series([1, 2, 3])) == 3.0
        finally:
            indicators.REGISTRY.pop("last_close")


class TestCompare:
    @pytest.mark.parametrize("op, value, expected", [
        (">=", 50, True), (">=", 51, False), (">", 50, False), (">", 49, True),
        ("<=", 50, True), ("<=", 49, False), ("<", 50, False), ("<", 51, True),
    ])
    def test_operators(self, op, value, expected):
        assert compare(50.0, op, value) is expected

    def test_a_missing_value_always_fails(self):
        assert compare(None, ">=", 0) is False

    def test_unknown_operator_is_an_error(self):
        with pytest.raises(ValueError, match="operator"):
            compare(1.0, "==", 1)


def with_custom(*filters):
    return {**RULES, "custom_filters": list(filters)}


RSI_INTRADAY = {"name": "X1_rsi", "indicator": "rsi", "source": "intraday",
                "params": {"period": 5}, "op": ">=", "value": 70}


class TestCustomFiltersInTheEntryCheck:
    def test_no_custom_filters_leaves_the_six_standard_checks_alone(self):
        assert set(run().checks) == {"D1", "D2", "D3", "I1", "I2", "I3"}

    def test_a_passing_custom_filter_joins_the_checks(self):
        r = run(rules=with_custom(RSI_INTRADAY))  # today's seven bars only rise
        assert r.checks["X1_rsi"] is True and r.passed

    def test_a_failing_custom_filter_blocks_the_entry_and_is_named(self):
        r = run(rules=with_custom({**RSI_INTRADAY, "op": "<", "value": 30}))
        assert not r.checks["X1_rsi"] and "X1_rsi" in r.reasons and not r.passed

    def test_the_daily_source_uses_prior_days_only(self):
        flat_daily = {"name": "X2", "indicator": "rsi", "source": "daily",
                      "params": {"period": 5}, "op": ">", "value": 0}
        r = run(daily=daily_frame(prior_close=100.0), rules=with_custom(flat_daily))
        assert r.checks["X2"] is True  # the final prior bar rose from the flat 90s

    def test_too_little_history_fails_closed(self):
        needs_a_lot = {**RSI_INTRADAY, "params": {"period": 50}}
        r = run(rules=with_custom(needs_a_lot))
        assert r.checks["X1_rsi"] is False and not r.passed

    def test_the_intraday_source_ignores_premarket_and_earlier_days(self):
        only_today = intraday_frame()
        r = run(intraday=only_today, rules=with_custom({**RSI_INTRADAY, "params": {"period": 6}}))
        assert r.checks["X1_rsi"] is True  # 7 regular bars give 6 changes

    def test_an_unknown_indicator_stops_the_symbol_instead_of_being_ignored(self):
        with pytest.raises(UnknownIndicator):
            run(rules=with_custom({**RSI_INTRADAY, "indicator": "nope"}))

    def test_an_unknown_source_is_an_error(self):
        with pytest.raises(ValueError, match="source"):
            run(rules=with_custom({**RSI_INTRADAY, "source": "weekly"}))
