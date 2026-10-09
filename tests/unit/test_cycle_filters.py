from datetime import datetime

import pandas as pd
import pytest

from trading_bot.cycle.filters import evaluate_filters, regular_session_today
from trading_bot.timeutil import ET

RULES = {
    "daily_filters": {
        "D1_above_prior_day_high": True,
        "D2_prior_close_above_sma200": True,
        "D3_min_gap_pct_from_prior_close": 3.0,
    },
    "intraday_filters": {
        "I1_above_premarket_high": True,
        "I2_above_today_hod": True,
        "I3_rvol_min": 2.0,
        "I3_rvol_lookback_days": 14,
    },
}
NOW = datetime(2026, 10, 8, 10, 7, tzinfo=ET)
TODAY = NOW.date()
PRIOR_DAYS = list(pd.bdate_range(end="2026-10-07", periods=14))
REGULAR = ["09:30", "09:35", "09:40", "09:45", "09:50", "09:55", "10:00"]


def daily_frame(prior_close=100.0, prior_high=101.0, n=205, base=90.0):
    """n daily bars up to yesterday: flat at `base`, with the last bar customised."""
    idx = pd.bdate_range(end="2026-10-07", periods=n)
    close = [base] * (n - 1) + [prior_close]
    high = [base + 1] * (n - 1) + [prior_high]
    return pd.DataFrame({"Open": close, "High": high, "Low": close, "Close": close,
                         "Volume": [1_000_000] * n}, index=idx)


def bar_rows(day, times, close, high=None, low=None, volume=1000):
    return [
        (pd.Timestamp(f"{day.date()} {t}", tz=ET), close, high or close, low or close, volume)
        for t in times
    ]


def intraday_frame(today_volume=2000, today_prices=None, premarket_high=102.0, history_days=PRIOR_DAYS):
    """14 prior days of volume 1000/bar, plus today's premarket + regular bars."""
    rows = []
    for d in history_days:
        rows += bar_rows(d, REGULAR, close=95.0)
    today = pd.Timestamp("2026-10-08")
    rows += bar_rows(today, ["08:00", "08:30"], close=100.0, high=premarket_high)
    prices = today_prices or [103.0, 103.5, 104.0, 104.5, 105.0, 105.5, 106.0]
    for t, p in zip(REGULAR, prices):
        rows += bar_rows(today, [t], close=p, high=p, low=p - 0.5, volume=today_volume)
    df = pd.DataFrame(rows, columns=["ts", "Close", "High", "Low", "Volume"]).set_index("ts")
    df["Open"] = df["Close"]
    return df


def run(daily=None, intraday=None, rules=RULES):
    return evaluate_filters(
        daily if daily is not None else daily_frame(),
        intraday if intraday is not None else intraday_frame(),
        rules, NOW,
    )


def test_all_six_filters_pass():
    r = run()
    assert r.passed and r.reasons == []
    assert set(r.checks) == {"D1", "D2", "D3", "I1", "I2", "I3"}
    assert all(r.checks.values())
    assert r.price == 106.0
    assert r.low_of_day == 102.5  # lowest regular-session low (first bar 103 - 0.5)


def test_d1_price_must_exceed_prior_day_high():
    r = run(daily=daily_frame(prior_high=110.0))
    assert not r.checks["D1"] and "D1" in r.reasons and not r.passed


def test_d2_prior_close_must_be_above_sma200():
    # prior close 80 vs 200-day average ~90
    r = run(daily=daily_frame(prior_close=80.0, prior_high=81.0))
    assert not r.checks["D2"]


def test_d2_fails_with_less_than_200_days_of_history():
    r = run(daily=daily_frame(n=150))
    assert not r.checks["D2"] and not r.passed


def test_d3_gap_below_threshold():
    # price 106 vs prior close 105 -> +0.95%
    r = run(daily=daily_frame(prior_close=105.0, prior_high=105.5))
    assert not r.checks["D3"]


def test_gap_uses_prior_close_not_todays_partial_daily_bar():
    daily = daily_frame()
    today_bar = pd.DataFrame(
        {"Open": [999.0], "High": [999.0], "Low": [999.0], "Close": [999.0], "Volume": [1]},
        index=[pd.Timestamp("2026-10-08")],
    )
    r = run(daily=pd.concat([daily, today_bar]))
    assert r.checks["D3"] and r.checks["D1"]


def test_i1_price_must_exceed_premarket_high():
    r = run(intraday=intraday_frame(premarket_high=110.0))
    assert not r.checks["I1"]


def test_i1_fails_without_premarket_data():
    df = intraday_frame()
    df = df[~((df.index.date == TODAY) & (df.index.time < pd.Timestamp("09:30").time()))]
    assert not run(intraday=df).checks["I1"]


def test_i2_price_must_exceed_todays_high_so_far():
    # last bar 104.0 is below an earlier high of 106.0
    r = run(intraday=intraday_frame(today_prices=[103, 106, 105, 104.5, 104.2, 104.1, 104.0]))
    assert not r.checks["I2"]


def test_i2_ignores_the_current_bar_itself():
    assert run().checks["I2"]  # steadily rising: last bar is the new high


def test_i3_relative_volume_threshold():
    # prior days: 7 bars * 1000 = 7000. today at 2 * that needs 2000/bar
    assert run(intraday=intraday_frame(today_volume=2000)).checks["I3"]
    assert not run(intraday=intraday_frame(today_volume=1900)).checks["I3"]


def test_i3_fails_with_insufficient_history():
    r = run(intraday=intraday_frame(history_days=PRIOR_DAYS[:5]))
    assert not r.checks["I3"]


def test_disabled_filters_are_skipped():
    rules = {
        "daily_filters": {**RULES["daily_filters"], "D1_above_prior_day_high": False},
        "intraday_filters": RULES["intraday_filters"],
    }
    assert run(daily=daily_frame(prior_high=110.0), rules=rules).checks["D1"]


def test_no_regular_session_bars_fails_cleanly():
    df = intraday_frame()
    df = df[~((df.index.date == TODAY) & (df.index.time >= pd.Timestamp("09:30").time()))]
    r = run(intraday=df)
    assert not r.passed and r.reasons == ["no regular-session data today"]


def test_regular_session_today_helper():
    reg = regular_session_today(intraday_frame(), TODAY)
    assert len(reg) == 7 and reg.index[0].strftime("%H:%M") == "09:30"
