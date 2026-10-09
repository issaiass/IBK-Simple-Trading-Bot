"""Swing lows on 5-minute bars."""
from collections.abc import Sequence


def swing_lows(lows: Sequence[float]) -> list[float]:
    """Lows strictly below the 2 bars before AND the 2 bars after, oldest first."""
    return [
        lows[i]
        for i in range(2, len(lows) - 2)
        if lows[i] < min(lows[i - 2], lows[i - 1], lows[i + 1], lows[i + 2])
    ]


def latest_swing_low(lows: Sequence[float]) -> float | None:
    found = swing_lows(lows)
    return found[-1] if found else None
