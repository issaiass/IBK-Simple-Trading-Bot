import pytest
from types import SimpleNamespace

from trading_bot.broker.client import IBKRClient
from trading_bot.settings import SafetyError


class FakeIB:
    """Order status moves PendingSubmit -> `final` after `settle_after` sleeps."""

    def __init__(self, final="Submitted", settle_after=2):
        self.events, self.final, self.settle_after, self.sleeps = [], final, settle_after, 0
        self.trade = SimpleNamespace(
            orderStatus=SimpleNamespace(status="PendingSubmit"), log=[]
        )

    def connect(self, host, port, clientId):
        self.events.append(("connect", host, port, clientId))

    def qualifyContracts(self, contract):
        self.events.append(("qualify", contract.symbol))
        return [contract]

    def placeOrder(self, contract, order):
        self.events.append(("place", contract.symbol, order))
        return self.trade

    def sleep(self, seconds):
        self.sleeps += 1
        if self.sleeps >= self.settle_after:
            self.trade.orderStatus.status = self.final

    def disconnect(self):
        self.events.append(("disconnect",))


def make(fake):
    return IBKRClient("127.0.0.1", 7497, 2, ib_factory=lambda: fake)


def test_connects_with_given_client_id():
    fake = FakeIB()
    make(fake)
    assert fake.events[0] == ("connect", "127.0.0.1", 7497, 2)


def test_qualifies_contract_before_placing_order():
    fake = FakeIB()
    make(fake).place_order("NVDA", "BUY", 3)
    kinds = [e[0] for e in fake.events]
    assert kinds.index("qualify") < kinds.index("place")


def test_places_outside_rth_market_order():
    fake = FakeIB()
    make(fake).place_order("NVDA", "BUY", 3)
    order = next(e[2] for e in fake.events if e[0] == "place")
    assert (order.orderType, order.action, order.totalQuantity) == ("MKT", "BUY", 3)
    assert order.outsideRth is True


def test_waits_until_status_leaves_pending_submit():
    fake = FakeIB(final="Filled", settle_after=3)
    trade = make(fake).place_order("NVDA", "BUY", 3)
    assert trade.orderStatus.status == "Filled" and fake.sleeps == 3


def test_gives_up_after_timeout_but_returns_trade():
    fake = FakeIB(settle_after=10_000)
    trade = make(fake).place_order("NVDA", "BUY", 3, timeout=2)
    assert trade.orderStatus.status == "PendingSubmit"
    assert fake.sleeps <= 5


def test_wait_for_fill_returns_once_filled():
    fake = FakeIB(final="Filled", settle_after=3)
    client = make(fake)
    trade = client.place_order("NVDA", "BUY", 1)
    fake.trade.orderStatus.status = "Submitted"
    fake.sleeps, fake.settle_after = 0, 2
    client.wait_for_fill(trade)
    assert trade.orderStatus.status == "Filled" and fake.sleeps == 2


def test_wait_for_fill_stops_on_rejection():
    fake = FakeIB(final="Cancelled", settle_after=1)
    client = make(fake)
    trade = client.place_order("NVDA", "BUY", 1)
    fake.sleeps = 0
    client.wait_for_fill(trade)
    assert fake.sleeps <= 1


def test_wait_for_fill_gives_up_after_timeout():
    fake = FakeIB(final="Submitted", settle_after=1)
    client = make(fake)
    trade = client.place_order("NVDA", "BUY", 1)
    fake.sleeps = 0
    client.wait_for_fill(trade, timeout=2)
    assert trade.orderStatus.status == "Submitted" and fake.sleeps <= 5


def test_cancel_open_orders_only_cancels_matching_symbol():
    cancelled = []
    fake = FakeIB()
    fake.reqAllOpenOrders = lambda: None
    fake.cancelOrder = cancelled.append
    fake.openTrades = lambda: [
        SimpleNamespace(contract=SimpleNamespace(symbol="NVDA"), order="stop-nvda"),
        SimpleNamespace(contract=SimpleNamespace(symbol="MU"), order="stop-mu"),
    ]
    make(fake).cancel_open_orders("NVDA")
    assert cancelled == ["stop-nvda"]


def test_disconnect_delegates_to_ib():
    fake = FakeIB()
    make(fake).disconnect()
    assert fake.events[-1] == ("disconnect",)


class TestAccountGuard:
    def guarded(self, accounts, paper):
        fake = FakeIB()
        fake.managedAccounts = lambda: accounts
        return fake, lambda: IBKRClient("127.0.0.1", 7497, 2, paper=paper, ib_factory=lambda: fake)

    def test_matching_account_connects(self):
        fake, build = self.guarded(["DU1234567"], paper=True)
        build()
        assert ("disconnect",) not in fake.events

    def test_mismatch_disconnects_and_aborts(self):
        fake, build = self.guarded(["U1234567"], paper=True)
        with pytest.raises(SafetyError, match="live account"):
            build()
        assert ("disconnect",) in fake.events

    def test_no_check_when_the_mode_is_not_given(self):
        fake = FakeIB()  # has no managedAccounts at all
        make(fake)
