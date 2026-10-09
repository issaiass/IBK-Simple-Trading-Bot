"""Stop-loss strategies and bracket (entry + protective stop) construction."""
from dataclasses import dataclass

from ib_async import MarketOrder, Order


@dataclass(frozen=True)
class PercentStop:
    """Fixed stop placed `pct` percent below the entry price."""

    pct: float

    def __post_init__(self):
        if not 0 < self.pct < 100:
            raise ValueError("pct must be between 0 and 100 (exclusive)")

    def stop_price(self, entry_price: float) -> float:
        return round(entry_price * (1 - self.pct / 100), 2)


@dataclass(frozen=True)
class AmountStop:
    """Fixed stop placed `amount` dollars below the entry price."""

    amount: float

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("amount must be positive")

    def stop_price(self, entry_price: float) -> float:
        price = round(entry_price - self.amount, 2)
        if price <= 0:
            raise ValueError("stop amount puts the stop at or below zero")
        return price


@dataclass(frozen=True)
class TrailingStop:
    """Stop that trails the price by a dollar `amount` or a `percent`."""

    amount: float | None = None
    percent: float | None = None

    def __post_init__(self):
        if (self.amount is None) == (self.percent is None):
            raise ValueError("give exactly one of amount or percent")
        if self.amount is not None and self.amount <= 0:
            raise ValueError("amount must be positive")
        if self.percent is not None and not 0 < self.percent < 100:
            raise ValueError("percent must be between 0 and 100 (exclusive)")


StopSpec = PercentStop | AmountStop | TrailingStop


def build_bracket(
    parent_id: int,
    quantity: float,
    stop: StopSpec,
    entry_price: float | None = None,
) -> tuple[Order, Order]:
    """Return (market BUY parent, protective SELL stop child) for fixed stops.

    The parent is not transmitted; the child is, which sends both together.
    Fixed stops (percent/amount) need `entry_price` to compute the stop level.
    Trailing stops can't be attached to a market parent (IB error 328); use
    build_trailing_stop after the entry fills.
    """
    if isinstance(stop, TrailingStop):
        raise ValueError("trailing stops cannot be bracketed; use build_trailing_stop")
    parent = MarketOrder("BUY", quantity)
    parent.orderId = parent_id
    parent.outsideRth = True
    parent.transmit = False

    child = Order(action="SELL", totalQuantity=quantity)
    child.orderId = parent_id + 1
    child.parentId = parent_id
    child.tif = "GTC"
    child.outsideRth = True
    child.transmit = True

    if entry_price is None:
        raise ValueError("entry_price is required for fixed stops")
    child.orderType = "STP"
    child.auxPrice = stop.stop_price(entry_price)
    return parent, child


def build_trailing_stop(order_id: int, quantity: float, stop: TrailingStop) -> Order:
    """Standalone GTC SELL trailing stop, placed after the entry has filled."""
    order = Order(action="SELL", totalQuantity=quantity)
    order.orderId = order_id
    order.orderType = "TRAIL"
    order.tif = "GTC"
    order.transmit = True
    if stop.amount is not None:
        order.auxPrice = stop.amount
    else:
        order.trailingPercent = stop.percent
    return order
