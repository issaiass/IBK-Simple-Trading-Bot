"""Live round trip on TWS paper: BUY then close, checking trades.csv rows.

Run: uv run pytest -m live tests/integration/test_live_trade_log.py
Needs the market open so orders fill, and places real paper orders.
"""
import pytest

from trading_bot.close import close
from trading_bot.settings import Settings
from trading_bot.trade import execute
from trading_bot.trades_log import TradeLog

pytestmark = pytest.mark.live
SYMBOL = "NVDA"


def test_buy_then_close_records_real_fills(tmp_path):
    settings = Settings.from_env()
    trades = TradeLog(tmp_path / "trades.csv")
    out = []

    try:
        assert execute(SYMBOL, "BUY", 1, settings, trades, out=out.append) == 0
        buy = trades.last_row()
        assert (buy["side"], buy["status"]) == ("BUY", "Filled"), out
        assert float(buy["fill_price"]) > 0
    finally:
        assert close(SYMBOL, settings, trades, out=out.append) == 0

    sell = trades.last_row()
    assert (sell["side"], sell["size"], sell["status"]) == ("SELL", "1", "Filled"), out
    assert float(sell["fill_price"]) > 0

    # flat afterwards: a second close finds nothing to sell
    assert close(SYMBOL, settings, trades, out=out.append) == 0
    assert out[-1] == "NO POSITION TO CLOSE"
