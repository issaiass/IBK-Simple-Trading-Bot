import pytest

from trading_bot.broker.stops import (
    AmountStop,
    PercentStop,
    TrailingStop,
    build_bracket,
    build_trailing_stop,
)


class TestStopPrices:
    def test_percent_stop_below_entry(self):
        assert PercentStop(2).stop_price(1000.0) == 980.0

    def test_percent_stop_rounds_to_cents(self):
        assert PercentStop(1).stop_price(333.33) == 330.0  # 329.9967 rounded

    def test_amount_stop_below_entry(self):
        assert AmountStop(15).stop_price(1000.0) == 985.0

    @pytest.mark.parametrize("pct", [0, -1, 100, 150])
    def test_percent_out_of_range_rejected(self, pct):
        with pytest.raises(ValueError):
            PercentStop(pct)

    @pytest.mark.parametrize("amount", [0, -5])
    def test_non_positive_amount_rejected(self, amount):
        with pytest.raises(ValueError):
            AmountStop(amount)

    def test_amount_not_below_entry_rejected(self):
        with pytest.raises(ValueError):
            AmountStop(1000).stop_price(1000.0)


class TestTrailingStopValidation:
    def test_needs_exactly_one_of_amount_or_percent(self):
        with pytest.raises(ValueError):
            TrailingStop()
        with pytest.raises(ValueError):
            TrailingStop(amount=5, percent=1)

    @pytest.mark.parametrize("kwargs", [{"amount": 0}, {"percent": 0}, {"percent": 100}])
    def test_invalid_values_rejected(self, kwargs):
        with pytest.raises(ValueError):
            TrailingStop(**kwargs)


class TestBuildBracket:
    def test_percent_bracket(self):
        parent, stop = build_bracket(7, 3, PercentStop(2), entry_price=1000.0)
        assert (parent.action, parent.orderType, parent.totalQuantity) == ("BUY", "MKT", 3)
        assert parent.orderId == 7 and parent.transmit is False
        assert (stop.action, stop.orderType, stop.totalQuantity) == ("SELL", "STP", 3)
        assert stop.auxPrice == 980.0
        assert stop.parentId == 7 and stop.orderId == 8 and stop.transmit is True
        assert stop.tif == "GTC"

    def test_amount_bracket(self):
        _, stop = build_bracket(7, 1, AmountStop(10), entry_price=500.0)
        assert stop.orderType == "STP" and stop.auxPrice == 490.0

    def test_trailing_cannot_be_bracketed(self):
        # IB only attaches trailing stops to limit/stop-limit parents
        with pytest.raises(ValueError):
            build_bracket(7, 1, TrailingStop(amount=5))


class TestBuildTrailingStop:
    def test_trailing_amount(self):
        stop = build_trailing_stop(9, 2, TrailingStop(amount=12.5))
        assert (stop.action, stop.orderType, stop.totalQuantity) == ("SELL", "TRAIL", 2)
        assert stop.auxPrice == 12.5 and stop.orderId == 9
        assert stop.parentId == 0 and stop.tif == "GTC" and stop.transmit is True

    def test_trailing_percent(self):
        stop = build_trailing_stop(9, 1, TrailingStop(percent=1.5))
        assert stop.orderType == "TRAIL" and stop.trailingPercent == 1.5

    def test_fixed_stop_requires_entry_price(self):
        with pytest.raises(ValueError):
            build_bracket(7, 1, PercentStop(2))
