"""Decide how to manage one open position (pure; no broker calls)."""
import math
from collections.abc import Sequence
from dataclasses import dataclass

from trading_bot.cycle.positions import (
    STATE_BE_NO_PARTIAL,
    STATE_BE_PARTIAL,
    STATE_PRE_BREAKEVEN,
    Position,
)
from trading_bot.cycle.swing import latest_swing_low

PARTIAL_STOP_FACTOR = 0.99  # stop on the remainder after a partial: 99% of entry
TRAIL_OFFSET = 0.01


@dataclass(frozen=True)
class Management:
    """What to do: cancel the old stop, sell `sell_qty` at market, place a new stop."""

    new_state: str
    new_stop_price: float
    new_qty: float  # shares the new stop protects
    sell_qty: int = 0


def manage_position(
    position: Position, price: float, lows_5m: Sequence[float], exit_rules: dict
) -> Management | None:
    if position.state == STATE_PRE_BREAKEVEN:
        return _pre_breakeven(position, price, exit_rules)
    return _trail(position, lows_5m)


def _pre_breakeven(p: Position, price: float, exit_rules: dict) -> Management | None:
    if price >= p.entry_price + exit_rules["breakeven_trigger_R"] * p.R:
        return Management(STATE_BE_NO_PARTIAL, round(p.entry_price, 2), p.qty)
    if price >= p.entry_price + exit_rules["partial_profit_trigger_R"] * p.R:
        sell = math.ceil(p.qty / 3)
        if sell < p.qty:  # never sell the whole position as a "partial"
            return Management(
                STATE_BE_PARTIAL,
                round(p.entry_price * PARTIAL_STOP_FACTOR, 2),
                p.qty - sell,
                sell,
            )
    return None


def _trail(p: Position, lows_5m: Sequence[float]) -> Management | None:
    swing = latest_swing_low(lows_5m)
    if swing is None:
        return None
    new_stop = round(swing - TRAIL_OFFSET, 2)
    if new_stop > p.stop_price:  # stops only ratchet up
        return Management(p.state, new_stop, p.qty)
    return None
