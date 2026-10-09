import pytest

from trading_bot.config import load_rules


@pytest.fixture(scope="module")
def rules():
    return load_rules()


def test_strategy_identity(rules):
    assert rules["strategy_name"] == "Trend Join Long"
    assert rules["direction"] == "long_only"
    assert rules["trade_timeframe"] == "5m"


def test_all_filter_keys_present(rules):
    assert set(rules["daily_filters"]) == {
        "D1_above_prior_day_high",
        "D2_prior_close_above_sma200",
        "D3_min_gap_pct_from_prior_close",
    }
    assert {"I1_above_premarket_high", "I2_above_today_hod", "I3_rvol_min"} <= set(
        rules["intraday_filters"]
    )


def test_time_gates_are_ordered(rules):
    t = rules["time_filter"]
    assert t["earliest_entry_et"] < t["latest_entry_et"] < t["force_close_et"]


def test_risk_limits_are_sane(rules):
    r = rules["risk"]
    assert 0 < r["max_risk_per_trade_pct"] <= 5
    assert r["max_concurrent_positions"] >= 1
