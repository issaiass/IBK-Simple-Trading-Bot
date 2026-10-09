import pytest

from trading_bot.cycle.manage import manage_position
from trading_bot.cycle.positions import (
    STATE_BE_NO_PARTIAL,
    STATE_BE_PARTIAL,
    STATE_PRE_BREAKEVEN,
    Position,
)

EXIT_RULES = {"partial_profit_trigger_R": 0.75, "breakeven_trigger_R": 1.0}


def pos(state=STATE_PRE_BREAKEVEN, qty=9, stop=98.0, **kw):
    return Position(
        symbol="NVDA", entry_price=100.0, entry_time_iso="2026-10-08T14:00:00+00:00",
        qty=qty, initial_stop=98.0, stop_order_id=7, state=state, R=2.0,
        stop_price=stop, **kw,
    )


class TestPreBreakeven:
    def test_below_075R_does_nothing(self):
        assert manage_position(pos(), 101.4, [], EXIT_RULES) is None

    def test_at_1R_moves_stop_to_entry_without_partial(self):
        m = manage_position(pos(), 102.0, [], EXIT_RULES)
        assert (m.sell_qty, m.new_stop_price, m.new_qty) == (0, 100.0, 9)
        assert m.new_state == STATE_BE_NO_PARTIAL

    def test_above_1R_also_breakeven_not_partial(self):
        m = manage_position(pos(), 110.0, [], EXIT_RULES)
        assert m.new_state == STATE_BE_NO_PARTIAL and m.sell_qty == 0

    def test_at_075R_sells_a_third_and_stops_at_99pct_of_entry(self):
        m = manage_position(pos(qty=9), 101.5, [], EXIT_RULES)
        assert m.sell_qty == 3
        assert (m.new_stop_price, m.new_qty) == (99.0, 6)
        assert m.new_state == STATE_BE_PARTIAL

    def test_partial_rounds_up(self):
        assert manage_position(pos(qty=10), 101.5, [], EXIT_RULES).sell_qty == 4

    def test_two_share_position_sells_one(self):
        m = manage_position(pos(qty=2), 101.5, [], EXIT_RULES)
        assert (m.sell_qty, m.new_qty) == (1, 1)

    def test_single_share_is_never_partialed_away(self):
        assert manage_position(pos(qty=1), 101.5, [], EXIT_RULES) is None

    def test_single_share_still_reaches_breakeven(self):
        m = manage_position(pos(qty=1), 102.0, [], EXIT_RULES)
        assert m.new_state == STATE_BE_NO_PARTIAL and m.new_stop_price == 100.0


@pytest.mark.parametrize("state", [STATE_BE_NO_PARTIAL, STATE_BE_PARTIAL])
class TestTrailing:
    lows = [110, 109, 105, 109, 110, 111]  # swing low 105

    def test_raises_stop_to_swing_low_minus_a_cent(self, state):
        m = manage_position(pos(state, stop=100.0), 112.0, self.lows, EXIT_RULES)
        assert m.new_stop_price == 104.99
        assert (m.sell_qty, m.new_qty, m.new_state) == (0, 9, state)

    def test_never_lowers_the_stop(self, state):
        assert manage_position(pos(state, stop=106.0), 112.0, self.lows, EXIT_RULES) is None

    def test_equal_level_is_not_a_move(self, state):
        assert manage_position(pos(state, stop=104.99), 112.0, self.lows, EXIT_RULES) is None

    def test_no_swing_low_no_move(self, state):
        assert manage_position(pos(state, stop=100.0), 112.0, [1, 2, 3, 4, 5], EXIT_RULES) is None

    def test_uses_the_newest_swing_low(self, state):
        lows = [110, 109, 105, 109, 110, 109, 107, 109, 110, 111]
        m = manage_position(pos(state, stop=100.0), 112.0, lows, EXIT_RULES)
        assert m.new_stop_price == 106.99
