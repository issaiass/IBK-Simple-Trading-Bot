"""Offline tests of the buy-then-trail flow using a fake IB."""
from types import SimpleNamespace

import pytest

from trading_bot.broker import orders
from trading_bot.broker.orders import OrderResult, buy_with_stop
from trading_bot.broker.stops import TrailingStop


class FakeIB:
    def __init__(self):
        self.placed = []
        self.client = SimpleNamespace(getReqId=lambda: 42)

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def placeOrder(self, contract, order):
        self.placed.append(order)
        return SimpleNamespace(orderStatus=SimpleNamespace(status="Submitted"))

    def sleep(self, seconds):
        pass


def entry(status):
    return OrderResult(
        order_id=41, quantity=1, status=status,
        fill_price=1000.0 if status == "Filled" else None, messages=(),
    )


@pytest.fixture
def ib():
    return FakeIB()


def test_trailing_stop_placed_after_entry_fills(ib, monkeypatch):
    monkeypatch.setattr(orders, "place_market_order", lambda *a, **k: entry("Filled"))
    result = buy_with_stop(ib, "MU", 1, TrailingStop(amount=10))
    assert len(ib.placed) == 1
    stop = ib.placed[0]
    assert (stop.action, stop.orderType, stop.auxPrice, stop.orderId) == (
        "SELL", "TRAIL", 10, 42,
    )
    assert result.stop_type == "TRAIL" and result.stop_price is None
    assert result.entry.fill_price == 1000.0


def test_trailing_percent_stop_placed(ib, monkeypatch):
    monkeypatch.setattr(orders, "place_market_order", lambda *a, **k: entry("Filled"))
    buy_with_stop(ib, "MU", 1, TrailingStop(percent=1.5))
    assert ib.placed[0].trailingPercent == 1.5


@pytest.mark.parametrize("status", ["Submitted", "Cancelled", "Inactive"])
def test_no_trailing_stop_when_entry_not_filled(ib, monkeypatch, status):
    monkeypatch.setattr(orders, "place_market_order", lambda *a, **k: entry(status))
    with pytest.raises(RuntimeError, match="not Filled"):
        buy_with_stop(ib, "MU", 1, TrailingStop(amount=10))
    assert ib.placed == []
