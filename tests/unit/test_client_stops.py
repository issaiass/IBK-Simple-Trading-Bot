from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from trading_bot.broker.client import IBKRClient

NOW = datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)


class FakeIB:
    def __init__(self):
        self.placed, self.cancelled, self.open = [], [], []
        self.fills, self.status = [], "Submitted"

    def connect(self, host, port, clientId):
        pass

    def qualifyContracts(self, contract):
        return [contract]

    def placeOrder(self, contract, order):
        order.orderId = 31
        self.placed.append(order)
        return SimpleNamespace(order=order, orderStatus=SimpleNamespace(status=self.status), log=[])

    def sleep(self, seconds):
        pass

    def reqOpenOrders(self):
        pass

    def openTrades(self):
        return self.open

    def cancelOrder(self, order):
        self.cancelled.append(order)

    def reqExecutions(self):
        return self.fills

    fresh_positions = None  # what the broker would report on a fresh request
    snapshots = None  # successive reqPositions() results, oldest first

    def reqPositions(self):
        if self.snapshots is not None:
            return self.snapshots.pop(0) if len(self.snapshots) > 1 else self.snapshots[0]
        return self.fresh_positions if self.fresh_positions is not None else self.positions()

    def positions(self):
        return [
            SimpleNamespace(contract=SimpleNamespace(symbol="NVDA"), position=10.0),
            SimpleNamespace(contract=SimpleNamespace(symbol="MU"), position=0.0),
            SimpleNamespace(contract=SimpleNamespace(symbol="AAPL"), position=-3.0),
        ]


@pytest.fixture
def fake():
    return FakeIB()


@pytest.fixture
def client(fake):
    return IBKRClient("127.0.0.1", 7497, 2, ib_factory=lambda: fake)


def fill(order_id, client_id=2, side="SLD", age_minutes=10, shares=10.0, price=100.0):
    return SimpleNamespace(execution=SimpleNamespace(
        orderId=order_id, clientId=client_id, side=side, shares=shares, price=price,
        time=NOW - timedelta(minutes=age_minutes),
    ))


def test_place_stop_sends_gtc_stop_sell_and_returns_order_id(client, fake):
    order_id = client.place_stop("NVDA", 6, 99.0)
    (order,) = fake.placed
    assert (order.action, order.orderType, order.totalQuantity, order.auxPrice) == ("SELL", "STP", 6, 99.0)
    assert order.tif == "GTC" and order_id == 31


@pytest.mark.parametrize("status", ["Cancelled", "Inactive"])
def test_place_stop_raises_when_rejected(client, fake, status):
    fake.status = status
    with pytest.raises(RuntimeError):
        client.place_stop("NVDA", 6, 99.0)


def test_cancel_order_id_cancels_the_matching_working_order(client, fake):
    mine, other = SimpleNamespace(orderId=7), SimpleNamespace(orderId=8)
    fake.open = [SimpleNamespace(order=other), SimpleNamespace(order=mine)]
    assert client.cancel_order_id(7) is True
    assert fake.cancelled == [mine]


def test_cancel_order_id_unknown_order_returns_false(client, fake):
    assert client.cancel_order_id(99) is False and fake.cancelled == []


def test_stop_fills_match_by_order_id_own_client_and_sells_in_window(client, fake):
    fake.fills = [
        fill(7, price=97.5),           # ours, recent -> yes
        fill(8, client_id=3),          # other client's order id 8 -> no
        fill(9, side="BOT"),           # a buy -> no
        fill(10, age_minutes=120),     # too old -> no
    ]
    assert client.stop_fill_prices(since=NOW - timedelta(hours=1)) == {7: 97.5}


def test_partial_executions_of_one_order_average_by_shares(client, fake):
    fake.fills = [fill(7, shares=10, price=100.0), fill(7, shares=30, price=96.0)]
    prices = client.stop_fill_prices(since=NOW - timedelta(hours=1))
    assert prices[7] == pytest.approx(97.0)


def test_held_positions_returns_only_long_positions(client):
    assert client.held_positions() == {"NVDA": 10.0}


def position(symbol, qty):
    return SimpleNamespace(contract=SimpleNamespace(symbol=symbol), position=qty)


def test_held_positions_requests_a_fresh_snapshot_not_the_stale_cache(client, fake):
    # the cached positions() list (NVDA) predates a fill made by another client id
    fake.fresh_positions = [position("BBY", 28.0)]
    assert client.held_positions() == {"BBY": 28.0}


def test_wait_for_position_polls_until_the_position_appears(client, fake):
    fake.snapshots = [[], [], [position("PM", 12.0)]]
    assert client.wait_for_position("PM", timeout=10) == 12.0


def test_wait_for_position_returns_immediately_when_already_held(client, fake):
    fake.fresh_positions = [position("PM", 12.0)]
    sleeps = []
    fake.sleep = sleeps.append
    assert client.wait_for_position("PM") == 12.0 and sleeps == []


def test_wait_for_position_gives_up_after_timeout(client, fake):
    fake.fresh_positions = []
    sleeps = []
    fake.sleep = sleeps.append
    assert client.wait_for_position("PM", timeout=3) == 0
    assert len(sleeps) == 3
