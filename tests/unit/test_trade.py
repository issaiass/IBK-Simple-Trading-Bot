from types import SimpleNamespace

import pytest

from trading_bot.settings import SafetyError, Settings
from trading_bot.trade import execute
from trading_bot.trades_log import TradeLog, TradeLogLocked

ENV = {
    "IBKR_HOST": "127.0.0.1", "IBKR_PORT": "7497", "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3", "PAPER_TRADING": "true",
    "PORTFOLIO_VALUE_USD": "25000", "MAX_TRADE_SIZE_USD": "2500",
    "MAX_TRADES_PER_DAY": "5", "MAX_RISK_PER_TRADE_PCT": "1.0",
}


def make_trade(status="Filled", fill=101.5, order_id=9):
    return SimpleNamespace(
        order=SimpleNamespace(orderId=order_id),
        orderStatus=SimpleNamespace(status=status, avgFillPrice=fill),
        log=[SimpleNamespace(status=status, message="because")],
    )


class FakeClient:
    instances = []

    def __init__(self, trade=None, connect_error=None, place_error=None, settle=None):
        self.trade, self.place_error, self.settle = trade, place_error, settle
        self.disconnected, self.args, self.waited = False, None, False
        FakeClient.instances.append(self)

    def wait_for_fill(self, trade):
        self.waited = True
        if self.settle:
            self.settle(trade)

    def place_order(self, symbol, side, quantity):
        self.args = (symbol, side, quantity)
        if self.place_error:
            raise self.place_error
        return self.trade

    def disconnect(self):
        self.disconnected = True


@pytest.fixture
def settings():
    return Settings.from_env(ENV)


@pytest.fixture
def trades(tmp_path):
    return TradeLog(tmp_path / "trades.csv")


def run(settings, trades, client, out=None):
    seen = []
    code = execute(
        "NVDA", "BUY", 5, settings, trades,
        client_factory=lambda host, port, cid, paper=None: (seen.append((host, port, cid)), client)[1],
        out=out or (lambda m: None),
    )
    return code, seen


def test_uses_exec_client_id_not_orchestrator_id(settings, trades):
    _, seen = run(settings, trades, FakeClient(make_trade()))
    assert seen == [("127.0.0.1", 7497, 3)]


def test_filled_order_is_logged_to_csv(settings, trades):
    client = FakeClient(make_trade("Filled", 101.5, 9))
    code, _ = run(settings, trades, client)
    row = trades.last_row()
    assert code == 0 and client.args == ("NVDA", "BUY", 5)
    assert (row["symbol"], row["side"], row["size"]) == ("NVDA", "BUY", "5")
    assert (row["fill_price"], row["order_id"], row["status"]) == ("101.5", "9", "Filled")
    assert row["timestamp_iso"].endswith("+00:00")  # UTC


def test_waits_for_fill_and_logs_the_real_fill_price(settings, trades):
    def fill(trade):
        trade.orderStatus.status, trade.orderStatus.avgFillPrice = "Filled", 235.57

    client = FakeClient(make_trade("Submitted", 0.0), settle=fill)
    run(settings, trades, client)
    row = trades.last_row()
    assert client.waited
    assert (row["status"], row["fill_price"]) == ("Filled", "235.57")


def test_sell_orders_are_recorded_too(settings, trades):
    client = FakeClient(make_trade("Filled", 235.57))
    code = execute(
        "NVDA", "SELL", 10, settings, trades,
        client_factory=lambda *a: client, out=lambda m: None,
    )
    row = trades.last_row()
    assert code == 0 and client.args == ("NVDA", "SELL", 10)
    assert (row["side"], row["size"], row["fill_price"]) == ("SELL", "10", "235.57")


def test_unfilled_submitted_order_logs_zero_fill_price(settings, trades):
    run(settings, trades, FakeClient(make_trade("Submitted", 0.0)))
    assert trades.last_row()["fill_price"] == "0"


@pytest.mark.parametrize("status", ["Cancelled", "ApiCancelled", "Inactive"])
def test_rejected_order_exits_nonzero_prints_log_and_skips_csv(settings, trades, status):
    lines = []
    code, _ = run(settings, trades, FakeClient(make_trade(status)), out=lines.append)
    assert code != 0
    assert any("because" in line for line in lines)
    assert trades.last_row() is None


def test_always_disconnects(settings, trades):
    ok, bad = FakeClient(make_trade()), FakeClient(make_trade("Cancelled"))
    run(settings, trades, ok)
    run(settings, trades, bad)
    assert ok.disconnected and bad.disconnected


def test_account_mismatch_aborts_instead_of_reporting_a_connection_failure(settings, trades):
    def wrong_account(host, port, cid, paper=None):
        raise SafetyError("ABORT: paper flag but live account")

    with pytest.raises(SafetyError):
        execute("NVDA", "BUY", 5, settings, trades, client_factory=wrong_account, out=lambda m: None)


def test_connection_error_exits_1(settings, trades):
    def boom(host, port, cid, paper=None):
        raise ConnectionRefusedError("TWS down")

    lines = []
    code = execute("NVDA", "BUY", 5, settings, trades, client_factory=boom, out=lines.append)
    assert code == 1 and any("TWS down" in line for line in lines)


def test_locked_trades_file_exits_1(settings, trades, monkeypatch):
    def locked(row):
        raise TradeLogLocked("locked")

    monkeypatch.setattr(trades, "append", locked)
    client = FakeClient(make_trade())
    code, _ = run(settings, trades, client)
    assert code == 1 and client.disconnected
