"""Yahoo Finance bars used by the cycle (screening and position management)."""
from datetime import date

import pandas as pd
import yfinance as yf

from trading_bot.cycle.filters import regular_session_today
from trading_bot.scanner.gappers import to_yahoo


class YahooMarketData:
    def entry_inputs(self, symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """(1y of daily bars, 1 month of 5m bars including premarket)."""
        ticker = yf.Ticker(to_yahoo(symbol))
        daily = ticker.history(period="1y", interval="1d", auto_adjust=False)
        intraday = ticker.history(period="1mo", interval="5m", prepost=True, auto_adjust=False)
        return daily, intraday

    def position_snapshot(self, symbol: str, today: date) -> tuple[float, list[float]]:
        """(latest price, today's regular-session 5m lows)."""
        intraday = yf.Ticker(to_yahoo(symbol)).history(
            period="1d", interval="5m", auto_adjust=False
        )
        regular = regular_session_today(intraday, today) if not intraday.empty else intraday
        if regular.empty:
            raise ValueError(f"no regular-session bars for {symbol} on {today}")
        return float(regular["Close"].iloc[-1]), [float(v) for v in regular["Low"]]
