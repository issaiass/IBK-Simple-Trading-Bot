import re
import subprocess
from datetime import datetime, timezone

import pytest

from trading_bot import bot
from trading_bot.settings import SafetyError, Settings
from trading_bot.timeutil import ET
from trading_bot.trades_log import TradeLog

ENV = {
    "IBKR_HOST": "127.0.0.1", "IBKR_PORT": "7497", "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3", "PAPER_TRADING": "true",
    "PORTFOLIO_VALUE_USD": "25000", "MAX_TRADE_SIZE_USD": "2500",
    "MAX_TRADES_PER_DAY": "5", "MAX_RISK_PER_TRADE_PCT": "1.0",
}
RULES = {"risk": {"max_position_size_pct_of_portfolio": 10}}
NOW = datetime(2026, 10, 8, 11, 0, 5, tzinfo=ET)
PASS = {"pass": True, "reasons": ["time gate ok", "no existing position"], "price": 100.0}
FAIL = {"pass": False, "reasons": ["already in position"], "price": 0.0}


class FakeClient:
    def __init__(self):
        self.ib, self.disconnected = object(), False

    def disconnect(self):
        self.disconnected = True


class Harness:
    def __init__(self, tmp_path, env=None, evaluation=PASS, trade_row=None):
        self.settings = Settings.from_env({**ENV, **(env or {})})
        self.trades = TradeLog(tmp_path / "trades.csv")
        self.client = FakeClient()
        self.lines, self.spawned, self.connected_with = [], [], []
        self.evaluation, self.trade_row = evaluation, trade_row

    def evaluator(self, symbol, ib):
        return self.evaluation

    def factory(self, host, port, client_id, paper=None):
        self.connected_with.append((host, port, client_id))
        return self.client

    def runner(self, symbol, side, size):
        self.spawned.append((symbol, side, size))
        if self.trade_row:
            self.trades.append(self.trade_row)
        return subprocess.CompletedProcess([], 0, stdout="trade stdout", stderr="")

    def run(self, symbol="NVDA", check_only=False):
        return bot.run(
            symbol, check_only, self.settings, RULES,
            trades=self.trades, clock=lambda: NOW, client_factory=self.factory,
            evaluator=self.evaluator, runner=self.runner, out=self.lines.append,
        )

    @property
    def text(self):
        return "\n".join(self.lines)


def buy_row(status="Filled", ts="2026-10-08T15:00:00+00:00"):
    return {"timestamp_iso": ts, "symbol": "NVDA", "side": "BUY", "size": 25,
            "fill_price": 100.0, "order_id": 1, "status": status}


@pytest.fixture
def h(tmp_path):
    return Harness(tmp_path)


def test_every_output_line_has_et_timestamp_prefix(h):
    h.run()
    assert h.lines and all(re.match(r"\[\d\d:\d\d:\d\d ET\] ", l) for l in h.lines)
    assert h.lines[0].startswith("[11:00:05 ET]")


def test_paper_flag_with_live_port_aborts_before_connecting(tmp_path):
    h = Harness(tmp_path, env={"IBKR_PORT": "7496"})
    with pytest.raises(SafetyError):
        h.run()
    assert h.connected_with == []


def test_daily_trade_cap_exits_without_connecting(tmp_path):
    h = Harness(tmp_path)
    for _ in range(5):
        h.trades.append(buy_row(ts="2026-10-08T15:00:00+00:00"))
    assert h.run() == 0
    assert h.connected_with == [] and "max trades" in h.text.lower()


def test_yesterdays_buys_do_not_count_toward_cap(tmp_path):
    h = Harness(tmp_path)
    for _ in range(5):
        h.trades.append(buy_row(ts="2026-10-07T15:00:00+00:00"))
    h.run()
    assert h.spawned


def test_connects_with_orchestrator_client_id(h):
    h.run()
    assert h.connected_with == [("127.0.0.1", 7497, 2)]


def test_check_only_prints_result_and_never_trades(h):
    assert h.run(check_only=True) == 0
    assert h.spawned == [] and h.client.disconnected
    assert "'pass': True" in h.text


def test_failed_evaluation_prints_reasons_and_never_trades(tmp_path):
    h = Harness(tmp_path, evaluation=FAIL)
    assert h.run() == 0
    assert h.spawned == [] and h.client.disconnected
    assert "already in position" in h.text


def test_too_small_position_never_trades(tmp_path):
    h = Harness(tmp_path, evaluation={**PASS, "price": 5000.0})
    assert h.run() == 0
    assert h.spawned == [] and "position too small" in h.text


def test_sizes_position_and_spawns_trade(h):
    h.run()
    # min(2500, 25000 * 10%) / $100 = 25 shares
    assert h.spawned == [("NVDA", "BUY", 25)]
    assert "trade stdout" in h.text


def test_reports_success_from_last_trade_row(tmp_path):
    h = Harness(tmp_path, trade_row=buy_row("Filled"))
    assert h.run() == 0
    assert "success" in h.text.lower()


def test_reports_failure_when_trade_not_logged(h):
    h.run()
    assert "failed" in h.text.lower()


def test_always_disconnects_even_when_spawn_fails(h):
    def boom(symbol, side, size):
        raise subprocess.TimeoutExpired("trade", 30)

    h.runner = boom
    assert h.run() == 1
    assert h.client.disconnected


def test_account_mismatch_aborts_instead_of_reporting_a_connection_failure(h):
    def wrong_account(host, port, client_id, paper=None):
        raise SafetyError("ABORT: paper flag but live account")

    h.factory = wrong_account
    with pytest.raises(SafetyError, match="live account"):
        h.run()


def test_connection_error_exits_1(h):
    def refuse(host, port, client_id, paper=None):
        raise ConnectionRefusedError("TWS down")

    h.factory = refuse
    assert h.run() == 1
    assert "TWS down" in h.text
