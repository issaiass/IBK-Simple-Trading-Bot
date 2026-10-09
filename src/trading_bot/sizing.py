"""Position sizing."""
import math

STOP_BELOW_LOD = 0.99  # initial stop = low of day minus 1%


def initial_stop(low_of_day: float) -> float:
    return round(low_of_day * STOP_BELOW_LOD, 2)


def risk_based_size(
    price: float,
    stop: float,
    portfolio_value_usd: float,
    risk_pct: float,
    max_position_pct: float,
) -> int:
    """Shares risking `risk_pct` of the portfolio per R, capped at `max_position_pct`."""
    r = price - stop
    if price <= 0 or r <= 0:
        return 0
    by_risk = math.floor(portfolio_value_usd * risk_pct / 100 / r)
    by_cap = math.floor(portfolio_value_usd * max_position_pct / 100 / price)
    return max(0, min(by_risk, by_cap))


def position_size(
    price: float,
    max_trade_size_usd: float,
    portfolio_value_usd: float,
    max_position_pct: float,
) -> int:
    """Whole shares affordable within the smaller of the two budgets."""
    if price <= 0:
        return 0
    budget = min(max_trade_size_usd, portfolio_value_usd * max_position_pct / 100)
    return int(budget / price)
