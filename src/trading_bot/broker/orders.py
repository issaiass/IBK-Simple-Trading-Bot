"""Market order helpers."""
import logging
import math
from dataclasses import dataclass

from ib_async import IB, MarketOrder, Stock

from trading_bot.broker.stops import (
    StopSpec,
    TrailingStop,
    build_bracket,
    build_trailing_stop,
)

FINAL_BAD = {"Cancelled", "ApiCancelled", "Inactive"}
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderResult:
    order_id: int
    quantity: float
    status: str
    fill_price: float | None
    messages: tuple[str, ...]

    @property
    def failed(self) -> bool:
        return self.status in FINAL_BAD


def place_market_order(
    ib: IB,
    symbol: str,
    action: str,
    quantity: float,
    settled: set[str],
    timeout: float = 10,
) -> OrderResult:
    """Place an outside-RTH market order and wait up to `timeout` seconds."""
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    order = MarketOrder(action, quantity)
    order.outsideRth = True
    trade = ib.placeOrder(contract, order)
    log.info("placed order %s", trade.order)

    waited = 0.0
    while trade.orderStatus.status not in settled and waited < timeout:
        ib.sleep(0.5)
        waited += 0.5

    messages = tuple(f"{e.status} {e.message}" for e in trade.log)
    for message in messages:
        log.info(message)
    status = trade.orderStatus
    return OrderResult(
        order_id=trade.order.orderId,
        quantity=quantity,
        status=status.status,
        fill_price=status.avgFillPrice if status.status == "Filled" else None,
        messages=messages,
    )


def buy_market(ib: IB, symbol: str, quantity: float) -> OrderResult:
    return place_market_order(
        ib, symbol, "BUY", quantity, {"Submitted", "Filled"} | FINAL_BAD
    )


def reference_price(ib: IB, contract: Stock) -> float:
    """Best available price: live/delayed last, else the previous close."""
    ib.qualifyContracts(contract)  # reqTickers needs the conId
    ib.reqMarketDataType(3)  # fall back to delayed data without a subscription
    ticker = ib.reqTickers(contract)[0]
    price = ticker.marketPrice()
    if math.isnan(price) or price <= 0:
        price = ticker.close
    if math.isnan(price) or price <= 0:
        raise RuntimeError(f"no price available for {contract.symbol}")
    return float(price)


@dataclass(frozen=True)
class BracketResult:
    entry: OrderResult
    stop_order_id: int
    stop_type: str
    stop_price: float | None  # None for trailing stops (managed by IB)


def buy_with_stop(
    ib: IB, symbol: str, quantity: float, stop: StopSpec, timeout: float = 10
) -> BracketResult:
    """Market BUY with a protective stop (percent, amount or trailing).

    Fixed stops go out as an atomic bracket. IB can't attach a trailing stop
    to a market order, so that entry is filled first, then the stop is placed.
    """
    contract = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(contract)
    if isinstance(stop, TrailingStop):
        return _buy_then_trail(ib, contract, quantity, stop, timeout)

    entry_price = reference_price(ib, contract)
    parent, child = build_bracket(ib.client.getReqId(), quantity, stop, entry_price)
    ib.client.reqIds(-1)  # keep IB's id counter ahead of the child id

    parent_trade = ib.placeOrder(contract, parent)
    child_trade = ib.placeOrder(contract, child)
    log.info("bracket parent=%s stop=%s", parent, child)

    settled = {"Submitted", "Filled"} | FINAL_BAD
    waited = 0.0
    while parent_trade.orderStatus.status not in settled and waited < timeout:
        ib.sleep(0.5)
        waited += 0.5
    ib.sleep(1)  # let the stop child register

    status = parent_trade.orderStatus
    entry = OrderResult(
        order_id=parent.orderId,
        quantity=quantity,
        status=status.status,
        fill_price=status.avgFillPrice if status.status == "Filled" else None,
        messages=tuple(f"{e.status} {e.message}" for e in parent_trade.log),
    )
    return BracketResult(
        entry=entry,
        stop_order_id=child.orderId,
        stop_type=child.orderType,
        stop_price=None if child.orderType == "TRAIL" else child.auxPrice,
    )


def _buy_then_trail(
    ib: IB, contract: Stock, quantity: float, stop: TrailingStop, timeout: float
) -> BracketResult:
    entry = place_market_order(
        ib, contract.symbol, "BUY", quantity, {"Filled"} | FINAL_BAD, timeout
    )
    if entry.status != "Filled":
        raise RuntimeError(
            f"entry order {entry.order_id} is {entry.status}, not Filled; "
            "no trailing stop placed (check TWS for the working order)"
        )
    order = build_trailing_stop(ib.client.getReqId(), quantity, stop)
    trade = ib.placeOrder(contract, order)
    ib.sleep(1)  # let the stop register
    log.info("trailing stop %s status %s", order, trade.orderStatus.status)
    return BracketResult(
        entry=entry, stop_order_id=order.orderId, stop_type="TRAIL", stop_price=None
    )


def close_position(ib: IB, symbol: str) -> OrderResult | None:
    """Cancel working orders on `symbol` and sell the full position.

    Returns None if there is no position.
    """
    for trade in ib.openTrades():
        if trade.contract.symbol == symbol:
            ib.cancelOrder(trade.order)  # drop protective stops first
    ib.sleep(1)
    position = next(
        (p for p in ib.positions() if p.contract.symbol == symbol and p.position),
        None,
    )
    if position is None:
        return None
    return place_market_order(
        ib, symbol, "SELL", abs(position.position), {"Filled"} | FINAL_BAD
    )
