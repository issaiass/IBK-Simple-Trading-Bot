import pytest

from trading_bot.sizing import position_size


def test_budget_is_capped_by_max_trade_size():
    # min(2500, 25000 * 10%) = 2500 -> 25 shares at $100
    assert position_size(100.0, 2500, 25000, 10) == 25


def test_budget_is_capped_by_portfolio_percentage():
    # min(5000, 25000 * 10%) = 2500
    assert position_size(100.0, 5000, 25000, 10) == 25
    # min(5000, 10000 * 10%) = 1000
    assert position_size(100.0, 5000, 10000, 10) == 10


def test_quantity_rounds_down():
    assert position_size(333.0, 2500, 25000, 10) == 7


def test_price_above_budget_gives_zero():
    assert position_size(1065.95, 1000, 25000, 10) == 0


@pytest.mark.parametrize("price", [0, -1])
def test_non_positive_price_gives_zero(price):
    assert position_size(price, 2500, 25000, 10) == 0
