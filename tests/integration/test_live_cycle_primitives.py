"""Live: the broker primitives the cycle relies on, across two client ids.

Run: uv run pytest -m live tests/integration/test_live_cycle_primitives.py
Reproduces the cycle's setup: a watcher connection (client 2) is already open
when ANOTHER client (3, like the trade subprocess) buys. The watcher must see
the new position, protect it with a stop, and manage that stop.
"""
import pytest

from trading_bot.broker.client import IBKRClient
from trading_bot.close import close
from trading_bot.settings import Settings
from trading_bot.trades_log import TradeLog

pytestmark = pytest.mark.live
SYMBOL = "NVDA"


def test_watcher_sees_a_fill_made_by_another_client_and_can_stop_it(tmp_path):
    settings = Settings.from_env()
    watcher = IBKRClient(settings.host, settings.port, settings.client_id)
    buyer = IBKRClient(settings.host, settings.port, settings.exec_client_id)
    try:
        assert SYMBOL not in watcher.held_positions(), "start flat"

        trade = buyer.place_order(SYMBOL, "BUY", 1)
        buyer.wait_for_fill(trade)
        assert trade.orderStatus.status == "Filled"

        # the cycle's check, with the watcher connected BEFORE the buy
        assert watcher.wait_for_position(SYMBOL) == 1

        stop_id = watcher.place_stop(SYMBOL, 1, round(trade.orderStatus.avgFillPrice * 0.95, 2))
        assert stop_id > 0
        assert watcher.cancel_order_id(stop_id) is True
        assert watcher.cancel_order_id(stop_id) is False  # already gone
    finally:
        buyer.disconnect()
        watcher.disconnect()
        # flatten: cancels leftover stops, sells, records into a temp CSV
        assert close(SYMBOL, settings, TradeLog(tmp_path / "trades.csv"), out=lambda m: None) == 0
