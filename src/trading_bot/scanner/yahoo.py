"""Yahoo Finance data source: prior close (daily) and latest price (5m, incl. premarket)."""
from datetime import date

import pandas as pd
import yfinance as yf

from trading_bot.scanner.gappers import Snapshot, to_yahoo
from trading_bot.timeutil import ET


def _closes(frame: pd.DataFrame, yahoo_symbol: str) -> pd.Series | None:
    """Close prices for one ticker with an Eastern-time index, or None."""
    if frame.empty:
        return None
    try:
        series = frame[yahoo_symbol]["Close"].dropna()
    except KeyError:
        return None
    index = pd.DatetimeIndex(series.index)
    index = index.tz_localize(ET) if index.tz is None else index.tz_convert(ET)
    return pd.Series(series.to_numpy(), index=index)


def build_snapshots(
    daily: pd.DataFrame, intraday: pd.DataFrame, symbols: list[str], today: date
) -> list[Snapshot]:
    """Pair each symbol's last close before `today` with its latest price today.

    Symbols with no prior close, or whose intraday data isn't from `today`
    (stale, e.g. before premarket opens), are skipped.
    """
    snapshots = []
    for symbol in symbols:
        yahoo_symbol = to_yahoo(symbol)
        daily_closes = _closes(daily, yahoo_symbol)
        intraday_closes = _closes(intraday, yahoo_symbol)
        if daily_closes is None or intraday_closes is None or intraday_closes.empty:
            continue

        prior = daily_closes[daily_closes.index.date < today]
        if prior.empty or intraday_closes.index[-1].date() != today:
            continue
        snapshots.append(
            Snapshot(symbol, float(prior.iloc[-1]), float(intraday_closes.iloc[-1]))
        )
    return snapshots


def fetch_snapshots(symbols: list[str], today: date) -> list[Snapshot]:
    """Download daily and premarket-inclusive 5m bars for all symbols at once."""
    tickers = [to_yahoo(s) for s in symbols]
    options = dict(group_by="ticker", auto_adjust=False, progress=False, threads=True)
    daily = yf.download(tickers, period="7d", interval="1d", **options)
    intraday = yf.download(tickers, period="1d", interval="5m", prepost=True, **options)
    return build_snapshots(daily, intraday, symbols, today)
