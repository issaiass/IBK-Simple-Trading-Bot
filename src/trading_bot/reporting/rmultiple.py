"""R-multiples: each closed trade's gain in units of the risk it was opened with.

    R = (exit - entry) / (entry - initial_stop)

The initial stop is taken from, in order: a stop_price column in trades.csv, the
decision log's "entered" event for that entry, and finally a proxy of 1% of the
entry price. Every result says which one it used, so estimates are never passed
off as measured values.
"""
from bisect import bisect_left
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from trading_bot.reporting.performance import ClosedTrade

PROXY_RISK_FRACTION = 0.01
STOP_MATCH_WINDOW = timedelta(minutes=10)  # an "entered" event follows its BUY within minutes
HISTOGRAM_EDGES = (-2, -1, 0, 1, 2, 3)  # buckets are inclusive on their upper edge
HISTOGRAM_LABELS = [
    "≤ -2R", "-2R to -1R", "-1R to 0R", "0R to +1R", "+1R to +2R", "+2R to +3R", "> +3R",
]


@dataclass(frozen=True)
class StopRecord:
    symbol: str
    time: datetime
    stop: float


@dataclass(frozen=True)
class RTrade:
    trade: ClosedTrade
    initial_stop: float
    r_multiple: float | None  # None when the stop was not below the entry
    r_source: str  # "trades_csv" | "decision_log" | "proxy"


@dataclass(frozen=True)
class Bucket:
    label: str
    lower: float | None  # None = open-ended
    upper: float | None
    count: int


def r_multiple(entry: float, exit_price: float, stop: float) -> float | None:
    risk = entry - stop
    if risk <= 0:
        return None
    return (exit_price - entry) / risk


def _logged_stop(trade: ClosedTrade, records: Sequence[StopRecord]) -> float | None:
    """The stop of the closest "entered" event shortly after this trade's BUY."""
    candidates = [
        r for r in records
        if r.symbol == trade.symbol and timedelta(0) <= r.time - trade.opened <= STOP_MATCH_WINDOW
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda r: r.time - trade.opened).stop


def attach_r(
    trades: Sequence[ClosedTrade], stop_records: Sequence[StopRecord] = ()
) -> list[RTrade]:
    result = []
    for trade in trades:
        if trade.stop_price is not None:
            stop, source = trade.stop_price, "trades_csv"
        elif (logged := _logged_stop(trade, stop_records)) is not None:
            stop, source = logged, "decision_log"
        else:
            stop, source = trade.entry_price * (1 - PROXY_RISK_FRACTION), "proxy"
        result.append(RTrade(
            trade, stop, r_multiple(trade.entry_price, trade.exit_price, stop), source,
        ))
    return result


def histogram(r_values: Iterable[float | None]) -> list[Bucket]:
    """Count trades per R bucket; trades with no defined R are skipped."""
    counts = [0] * len(HISTOGRAM_LABELS)
    for value in r_values:
        if value is not None:
            counts[bisect_left(HISTOGRAM_EDGES, value)] += 1
    bounds = [None, *HISTOGRAM_EDGES, None]
    return [
        Bucket(label, bounds[i], bounds[i + 1], counts[i])
        for i, label in enumerate(HISTOGRAM_LABELS)
    ]
