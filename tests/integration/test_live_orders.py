"""Live tests against TWS paper trading (port 7497). Run: uv run pytest -m live"""
import pytest

from trading_bot.broker.connection import connected
from trading_bot.broker.orders import buy_market, buy_with_stop, close_position
from trading_bot.broker.stops import AmountStop, PercentStop, TrailingStop

pytestmark = pytest.mark.live


def test_connect():
    with connected(client_id=99) as ib:
        assert ib.isConnected()
        assert ib.managedAccounts()


def test_buy_one_share_of_mu():
    with connected(client_id=10) as ib:
        result = buy_market(ib, "MU", 1)
    print(f"ORDERED: 1 share MU, status {result.status}. Check TWS positions panel.")
    assert not result.failed


@pytest.mark.parametrize(
    "stop, order_type",
    [
        (PercentStop(2), "STP"),
        (AmountStop(20), "STP"),
        (TrailingStop(amount=20), "TRAIL"),
        (TrailingStop(percent=2), "TRAIL"),
    ],
    ids=["percent", "amount", "trailing-amount", "trailing-percent"],
)
def test_buy_mu_with_stop(stop, order_type):
    with connected(client_id=12) as ib:
        try:
            result = buy_with_stop(ib, "MU", 1, stop)
            assert not result.entry.failed
            assert result.stop_type == order_type
            working = {t.order.orderId for t in ib.openTrades()}
            assert result.stop_order_id in working
        finally:
            close_position(ib, "MU")  # cancels the stop and flattens


def test_close_mu_position():
    with connected(client_id=11) as ib:
        result = close_position(ib, "MU")
    if result is not None:
        assert not result.failed
    print("CLOSED: position flat. Verify in TWS.")
