from types import SimpleNamespace

import pytest

from trading_bot.broker.orders import reference_price


class FakeIB:
    def __init__(self, market=float("nan"), close=float("nan")):
        self.events = []
        self.ticker = SimpleNamespace(marketPrice=lambda: market, close=close)

    def reqMarketDataType(self, kind):
        self.events.append("data_type")

    def qualifyContracts(self, contract):
        self.events.append("qualify")
        contract.conId = 1
        return [contract]

    def reqTickers(self, contract):
        # ib_async hashes the contract, which needs a conId
        assert contract.conId, "contract must be qualified before reqTickers"
        self.events.append("tickers")
        return [self.ticker]


def contract():
    return SimpleNamespace(symbol="NVDA", conId=0)


def test_qualifies_contract_before_requesting_quote():
    ib = FakeIB(market=120.5)
    assert reference_price(ib, contract()) == 120.5
    assert ib.events.index("qualify") < ib.events.index("tickers")


def test_falls_back_to_previous_close():
    assert reference_price(FakeIB(close=118.0), contract()) == 118.0


def test_raises_when_no_price_available():
    with pytest.raises(RuntimeError, match="no price"):
        reference_price(FakeIB(), contract())
