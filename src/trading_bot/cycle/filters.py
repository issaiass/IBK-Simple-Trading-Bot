"""The six entry filters from rules.json: D1-D3 (daily) and I1-I3 (intraday),
plus any optional `custom_filters` (see indicators.py)."""
from dataclasses import dataclass
from datetime import date, datetime, time

import pandas as pd

from trading_bot.cycle.indicators import evaluate_custom_filters
from trading_bot.timeutil import ET

REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
SMA_DAYS = 200


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    checks: dict[str, bool]
    reasons: list[str]  # names of the filters that failed
    price: float
    low_of_day: float


def _to_et(frame: pd.DataFrame) -> pd.DataFrame:
    index = pd.DatetimeIndex(frame.index)
    index = index.tz_localize(ET) if index.tz is None else index.tz_convert(ET)
    return frame.set_axis(index)


def regular_session_today(intraday: pd.DataFrame, day: date) -> pd.DataFrame:
    frame = _to_et(intraday)
    times = frame.index.time
    return frame[(frame.index.date == day) & (times >= REGULAR_OPEN) & (times < REGULAR_CLOSE)]


def _rvol(intraday: pd.DataFrame, regular: pd.DataFrame, day: date, lookback: int) -> float | None:
    """Today's cumulative volume vs the same time-of-day average of prior days."""
    cutoff = regular.index[-1].time()
    times = intraday.index.time
    prior = intraday[
        (intraday.index.date < day) & (times >= REGULAR_OPEN) & (times <= cutoff)
    ]
    per_day = prior.groupby(prior.index.date)["Volume"].sum()
    if len(per_day) < lookback:
        return None
    average = per_day.tail(lookback).mean()
    return float(regular["Volume"].sum() / average) if average > 0 else None


def evaluate_filters(
    daily: pd.DataFrame, intraday: pd.DataFrame, rules: dict, now: datetime
) -> FilterResult:
    """Run all six filters for one symbol. A disabled (false) filter counts as passed."""
    day = now.date()
    intraday = _to_et(intraday)
    regular = regular_session_today(intraday, day)
    if regular.empty:
        return FilterResult(False, {}, ["no regular-session data today"], 0.0, 0.0)

    price = float(regular["Close"].iloc[-1])
    low_of_day = float(regular["Low"].min())
    d, i = rules["daily_filters"], rules["intraday_filters"]

    prior = daily[pd.DatetimeIndex(daily.index).date < day]
    have_prior = not prior.empty
    prior_close = float(prior["Close"].iloc[-1]) if have_prior else 0.0
    prior_high = float(prior["High"].iloc[-1]) if have_prior else float("inf")

    premarket = intraday[(intraday.index.date == day) & (intraday.index.time < REGULAR_OPEN)]
    earlier_bars = regular.iloc[:-1]
    rvol = _rvol(intraday, regular, day, i["I3_rvol_lookback_days"])

    checks = {
        "D1": not d["D1_above_prior_day_high"] or price > prior_high,
        "D2": not d["D2_prior_close_above_sma200"]
        or (len(prior) >= SMA_DAYS and prior_close > prior["Close"].tail(SMA_DAYS).mean()),
        "D3": have_prior
        and prior_close > 0
        and (price - prior_close) / prior_close * 100 >= d["D3_min_gap_pct_from_prior_close"],
        "I1": not i["I1_above_premarket_high"]
        or (not premarket.empty and price > float(premarket["High"].max())),
        "I2": not i["I2_above_today_hod"]
        or earlier_bars.empty
        or price > float(earlier_bars["High"].max()),
        "I3": rvol is not None and rvol >= i["I3_rvol_min"],
    }
    checks = {name: bool(ok) for name, ok in checks.items()}
    checks |= evaluate_custom_filters(
        rules.get("custom_filters", []),
        {"daily": prior["Close"], "intraday": regular["Close"]},
    )
    reasons = [name for name, ok in checks.items() if not ok]
    return FilterResult(not reasons, checks, reasons, price, low_of_day)
