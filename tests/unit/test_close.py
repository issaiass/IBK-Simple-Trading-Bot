from types import SimpleNamespace

import pytest

from trading_bot.close import close
from trading_bot.settings import Settings
from trading_bot.trades_log import TradeLog

ENV = {
    "IBKR_HOST": "127.0.0.1", "IBKR_PORT": "7497", "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3", "PAPER_TRADING": "true",
    "PORTFOLIO_VALUE_USD": "25000", "MAX_TRADE_SIZE_USD": "2500",
    "MAX_TRADES_PER_DAY": "5", "MAX_RISK_PER_TRADE_PCT": "1.0",
}


def position(symbol, qty):
    return SimpleNamespace(contract=SimpleNamespace(symbol=symbol), position=qty)


class FakeClient:
    def __init__(self, positions, fill=235.57):
        self.ib = SimpleNamespace(positions=lambda: positions)
        self.fill, self.orders, self.cancelled = fill, [], []
        self.disconnected, self.waited = False, False
        self.trade = SimpleNamespace(
            order=SimpleNamespace(orderId=8),
            orderStatus=SimpleNamespace(status="Submitted", avgFillPrice=0.0),
            log=[],
        )

    def cancel_open_orders(self, symbol):
        self.cancelled.append(symbol)

    def place_order(self, symbol, side, quantity):
        self.orders.append((symbol, side, quantity))
        return self.trade

    def wait_for_fill(self, trade):
        self.waited = True
        trade.orderStatus.status, trade.orderStatus.avgFillPrice = "Filled", self.fill

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def settings():
    return Settings.from_env(ENV)


@pytest.fixture
def trades(tmp_path):
    return TradeLog(tmp_path / "trades.csv")


def run(settings, trades, client, lines=None):
    seen = []
    code = close(
        "NVDA", settings, trades,
        client_factory=lambda host, port, cid, paper=None: (seen.append(cid), client)[1],
        out=(lines.append if lines is not None else lambda m: None),
    )
    return code, seen


def test_sells_full_long_position_and_records_real_fill(settings, trades):
    client = FakeClient([position("NVDA", 10.0), position("MU", 3.0)])
    code, _ = run(settings, trades, client)
    row = trades.last_row()
    assert code == 0 and client.orders == [("NVDA", "SELL", 10)]
    assert (row["symbol"], row["side"], row["size"]) == ("NVDA", "SELL", "10")
    assert (row["fill_price"], row["status"]) == ("235.57", "Filled")


def test_uses_executor_client_id(settings, trades):
    _, seen = run(settings, trades, FakeClient([position("NVDA", 1.0)]))
    assert seen == [3]


def test_cancels_working_orders_before_selling(settings, trades):
    client = FakeClient([position("NVDA", 10.0)])
    run(settings, trades, client)
    assert client.cancelled == ["NVDA"]


def test_no_position_prints_message_and_logs_nothing(settings, trades):
    client, lines = FakeClient([position("MU", 3.0)]), []
    code, _ = run(settings, trades, client, lines)
    assert code == 0 and client.orders == []
    assert any("NO POSITION TO CLOSE" in line for line in lines)
    assert trades.last_row() is None


def test_short_position_is_not_sold(settings, trades):
    client = FakeClient([position("NVDA", -5.0)])
    run(settings, trades, client)
    assert client.orders == []


def test_always_disconnects(settings, trades):
    for positions in ([position("NVDA", 1.0)], []):
        client = FakeClient(positions)
        run(settings, trades, client)
        assert client.disconnected
