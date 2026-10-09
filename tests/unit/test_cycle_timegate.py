from datetime import datetime

import pytest

from trading_bot.cycle.timegate import time_gate
from trading_bot.timeutil import ET

RULES = {"time_filter": {
    "earliest_entry_et": "10:05", "latest_entry_et": "15:30", "force_close_et": "15:51",
}}


def at(day, hour, minute, second=0):
    return datetime(2026, 10, day, hour, minute, second, tzinfo=ET)


@pytest.mark.parametrize("when, expected", [
    (at(10, 12, 0), "weekend"),        # Saturday
    (at(11, 12, 0), "weekend"),        # Sunday
    (at(8, 0, 0), "too_early"),
    (at(8, 9, 59, 59), "too_early"),
    (at(8, 10, 0), "manage_only"),
    (at(8, 10, 4, 59), "manage_only"),
    (at(8, 10, 5), "ok"),
    (at(8, 12, 0), "ok"),
    (at(8, 15, 29, 59), "ok"),
    (at(8, 15, 30), "manage_only"),
    (at(8, 15, 50, 59), "manage_only"),
    (at(8, 15, 51), "force_close"),
    (at(8, 15, 59, 59), "force_close"),
    (at(8, 16, 0), "closed"),
    (at(8, 20, 0), "closed"),
])
def test_time_gate(when, expected):
    assert time_gate(when, RULES) == expected


def test_weekend_wins_over_time_of_day():
    assert time_gate(at(10, 10, 30), RULES) == "weekend"
