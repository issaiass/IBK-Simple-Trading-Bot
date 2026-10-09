import pytest

from trading_bot.sizing import initial_stop, risk_based_size


def test_initial_stop_is_one_percent_below_low_of_day():
    assert initial_stop(50.0) == 49.5
    assert initial_stop(102.5) == 101.47  # 101.475 rounds to cents


def test_risk_limited_size():
    # R = 100 - 99 = 1; risk $ = 25000 * 1% = 250 -> 250 shares; cap 10% = 25 shares... use big portfolio
    assert risk_based_size(100.0, 99.0, 100_000, 1.0, 100) == 1000


def test_position_cap_limits_size():
    # R=2 -> 125 by risk; cap = 25000 * 10% / 100 = 25
    assert risk_based_size(100.0, 98.0, 25_000, 1.0, 10) == 25


def test_wide_stop_makes_risk_the_limit():
    # R=20 -> 12 by risk (250/20=12.5); cap 25
    assert risk_based_size(100.0, 80.0, 25_000, 1.0, 10) == 12


def test_expensive_stock_limited_by_cap():
    # price 1000, R=10 -> 25 by risk; cap = 2500/1000 = 2
    assert risk_based_size(1000.0, 990.0, 25_000, 1.0, 10) == 2


@pytest.mark.parametrize("stop", [100.0, 101.0])
def test_stop_at_or_above_price_gives_zero(stop):
    assert risk_based_size(100.0, stop, 25_000, 1.0, 10) == 0


def test_size_below_one_share_is_zero():
    assert risk_based_size(3000.0, 2900.0, 25_000, 1.0, 10) == 0
