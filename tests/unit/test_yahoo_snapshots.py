"""Converting yfinance frames into snapshots (offline, hand-built frames)."""
from datetime import date

import pandas as pd

from trading_bot.scanner.yahoo import build_snapshots
from trading_bot.timeutil import ET

TODAY = date(2026, 10, 8)


def frame(per_ticker: dict[str, list], index) -> pd.DataFrame:
    """MultiIndex columns (Ticker, Field), like yf.download(group_by='ticker')."""
    cols = {}
    for ticker, closes in per_ticker.items():
        cols[(ticker, "Close")] = closes
    df = pd.DataFrame(cols, index=index)
    df.columns = pd.MultiIndex.from_tuples(df.columns)
    return df


def daily(per_ticker):
    idx = pd.to_datetime(["2026-10-06", "2026-10-07", "2026-10-08"])
    return frame(per_ticker, idx)


def intraday(per_ticker, day="2026-10-08"):
    idx = pd.DatetimeIndex(
        [f"{day} 04:00", f"{day} 04:05", f"{day} 04:10"], tz=ET
    )
    return frame(per_ticker, idx)


def test_uses_last_daily_close_before_today_and_latest_intraday_price():
    d = daily({"NVDA": [230.0, 240.0, 999.0]})  # today's partial daily bar ignored
    i = intraday({"NVDA": [241.0, 245.0, 247.2]})
    (s,) = build_snapshots(d, i, ["NVDA"], TODAY)
    assert (s.symbol, s.prior_close, s.price) == ("NVDA", 240.0, 247.2)


def test_skips_nan_intraday_bars():
    d = daily({"MU": [1.0, 100.0, 101.0]})
    i = intraday({"MU": [104.0, float("nan"), float("nan")]})
    (s,) = build_snapshots(d, i, ["MU"], TODAY)
    assert s.price == 104.0


def test_maps_yahoo_symbols_back_to_ibkr_format():
    d = daily({"BRK-B": [1.0, 500.0, 501.0]})
    i = intraday({"BRK-B": [505.0, 506.0, 507.0]})
    (s,) = build_snapshots(d, i, ["BRK B"], TODAY)
    assert s.symbol == "BRK B"


def test_stale_intraday_data_is_skipped():
    d = daily({"AAPL": [1.0, 200.0, 201.0]})
    i = intraday({"AAPL": [210.0, 211.0, 212.0]}, day="2026-10-07")  # yesterday
    assert build_snapshots(d, i, ["AAPL"], TODAY) == []


def test_symbol_missing_from_download_is_skipped():
    d = daily({"AAPL": [1.0, 200.0, 201.0]})
    i = intraday({"AAPL": [210.0, 211.0, 212.0]})
    result = build_snapshots(d, i, ["AAPL", "ZZZZ"], TODAY)
    assert [s.symbol for s in result] == ["AAPL"]


def test_symbol_with_no_prior_close_is_skipped():
    idx = pd.to_datetime(["2026-10-08"])
    d = frame({"NEW": [50.0]}, idx)  # only today's bar, no history
    i = intraday({"NEW": [51.0, 52.0, 53.0]})
    assert build_snapshots(d, i, ["NEW"], TODAY) == []


def test_empty_downloads_give_no_snapshots():
    assert build_snapshots(pd.DataFrame(), pd.DataFrame(), ["AAPL"], TODAY) == []
