"""Market-hours gate. Kept dependency-light so off-hours runs exit instantly."""
from datetime import datetime, time

from trading_bot.timeutil import parse_hhmm

MARKET_OPEN = time(10, 0)  # the cycle starts managing at 10:00 ET
MARKET_CLOSE = time(16, 0)
INACTIVE = {"weekend", "too_early", "closed"}


def time_gate(now: datetime, rules: dict) -> str:
    """One of: weekend, too_early, closed, manage_only, force_close, ok."""
    if now.weekday() >= 5:
        return "weekend"
    t = now.time()
    window = rules["time_filter"]
    if t < MARKET_OPEN:
        return "too_early"
    if t >= MARKET_CLOSE:
        return "closed"
    if t >= parse_hhmm(window["force_close_et"]):
        return "force_close"
    if t >= parse_hhmm(window["latest_entry_et"]):
        return "manage_only"
    if t >= parse_hhmm(window["earliest_entry_et"]):
        return "ok"
    return "manage_only"
