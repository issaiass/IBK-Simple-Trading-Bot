"""Thin IBKR client used by the orchestrator and the executor."""
from collections.abc import Callable
from datetime import datetime

from ib_async import IB, MarketOrder, StopOrder, Stock, Trade

from trading_bot.settings import check_account_matches_mode

PENDING = {"PendingSubmit", "PendingCancel", "ApiPending"}
DONE = {"Filled", "Cancelled", "ApiCancelled", "Inactive"}


class IBKRClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        paper: bool | None = None,
        ib_factory: Callable[[], IB] = IB,
    ):
        self.client_id = client_id
        self.ib = ib_factory()
        self.ib.connect(host, port, clientId=client_id)
        if paper is not None:  # the port can lie; the account id cannot
            try:
                check_account_matches_mode(paper, list(self.ib.managedAccounts()))
            except Exception:
                self.ib.disconnect()
                raise

    def place_order(
        self, symbol: str, side: str, quantity: int, timeout: float = 10
    ) -> Trade:
        """Market order (outside RTH); waits for the status to leave pending."""
        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        order = MarketOrder(side, quantity)
        order.outsideRth = True
        trade = self.ib.placeOrder(contract, order)

        waited = 0.0
        while trade.orderStatus.status in PENDING and waited < timeout:
            self.ib.sleep(0.5)
            waited += 0.5
        return trade

    def wait_for_fill(self, trade: Trade, timeout: float = 10) -> None:
        """Wait until the order is filled or rejected, up to `timeout` seconds."""
        waited = 0.0
        while trade.orderStatus.status not in DONE and waited < timeout:
            self.ib.sleep(0.5)
            waited += 0.5

    def place_stop(self, symbol: str, quantity: float, stop_price: float) -> int:
        """GTC protective SELL stop. Returns its order id; raises if rejected."""
        contract = Stock(symbol, "SMART", "USD")
        self.ib.qualifyContracts(contract)
        order = StopOrder("SELL", quantity, stop_price)
        order.tif = "GTC"
        order.outsideRth = True
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1)
        if trade.orderStatus.status in DONE - {"Filled"}:
            raise RuntimeError(
                f"stop for {symbol} was {trade.orderStatus.status}: "
                + "; ".join(e.message for e in trade.log if e.message)
            )
        return order.orderId

    def cancel_order_id(self, order_id: int) -> bool:
        """Cancel one of this client's working orders. False if it isn't working."""
        self.ib.reqOpenOrders()
        for trade in self.ib.openTrades():
            if trade.order.orderId == order_id:
                self.ib.cancelOrder(trade.order)
                self.ib.sleep(1)
                return True
        return False

    def held_positions(self) -> dict[str, float]:
        """Long positions by symbol, from a fresh request.

        ib.positions() is a cache that lags fills made by other client ids (the
        trade subprocess), so it can miss a position that was just bought.
        """
        return {
            p.contract.symbol: p.position for p in self.ib.reqPositions() if p.position > 0
        }

    def wait_for_position(self, symbol: str, timeout: int = 20) -> float:
        """Poll until `symbol` is held (seconds); 0 if it never appears."""
        waited = 0
        while True:
            quantity = self.held_positions().get(symbol, 0)
            if quantity > 0 or waited >= timeout:
                return quantity
            self.ib.sleep(1)
            waited += 1

    def stop_fill_prices(self, since: datetime) -> dict[int, float]:
        """This client's SELL executions since `since` (aware datetime).

        Maps order id -> average fill price (partial executions are averaged by
        shares). Order ids repeat across clients, so executions from other client
        ids are ignored.
        """
        totals: dict[int, tuple[float, float]] = {}
        for f in self.ib.reqExecutions():
            e = f.execution
            if e.clientId == self.client_id and e.side == "SLD" and e.time >= since:
                shares, notional = totals.get(e.orderId, (0.0, 0.0))
                totals[e.orderId] = (shares + e.shares, notional + e.shares * e.price)
        return {oid: notional / shares for oid, (shares, notional) in totals.items() if shares > 0}

    def cancel_open_orders(self, symbol: str) -> None:
        """Cancel visible working orders (e.g. protective stops) on `symbol`."""
        self.ib.reqAllOpenOrders()
        for trade in self.ib.openTrades():
            if trade.contract.symbol == symbol:
                self.ib.cancelOrder(trade.order)
        self.ib.sleep(1)

    def disconnect(self) -> None:
        self.ib.disconnect()
