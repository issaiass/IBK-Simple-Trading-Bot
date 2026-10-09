from trading_bot.cycle.swing import latest_swing_low, swing_lows


def test_finds_a_swing_low():
    assert swing_lows([5, 4, 3, 4, 5]) == [3]


def test_needs_two_lower_bars_on_each_side():
    assert swing_lows([5, 3, 4, 5, 6]) == []          # only 1 bar before
    assert swing_lows([6, 5, 4, 3, 4]) == []          # only 1 bar after


def test_ties_are_not_swing_lows():
    assert swing_lows([5, 4, 3, 3, 5]) == []
    assert swing_lows([5, 4, 3, 4, 3]) == []


def test_multiple_swing_lows_in_time_order():
    lows = [9, 8, 5, 8, 9, 8, 7, 8, 9, 10]
    assert swing_lows(lows) == [5, 7]


def test_latest_swing_low_is_the_newest():
    assert latest_swing_low([9, 8, 5, 8, 9, 8, 7, 8, 9, 10]) == 7


def test_latest_swing_low_none_without_one():
    assert latest_swing_low([1, 2, 3, 4, 5]) is None
    assert latest_swing_low([]) is None
    assert latest_swing_low([1, 2]) is None
