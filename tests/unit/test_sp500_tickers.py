import re

from trading_bot.sp500_tickers import SP500_TICKERS

IBKR_SYMBOL = re.compile(r"^[A-Z]{1,5}( [A-Z])?$")


def test_is_a_list_of_strings():
    assert isinstance(SP500_TICKERS, list)
    assert all(isinstance(t, str) for t in SP500_TICKERS)


def test_has_about_503_entries():
    assert 500 <= len(SP500_TICKERS) <= 506


def test_sorted_and_unique():
    assert SP500_TICKERS == sorted(SP500_TICKERS)
    assert len(set(SP500_TICKERS)) == len(SP500_TICKERS)


def test_all_symbols_are_in_ibkr_format():
    bad = [t for t in SP500_TICKERS if not IBKR_SYMBOL.match(t)]
    assert bad == []


def test_class_b_shares_use_a_space_not_a_hyphen_or_dot():
    assert "BRK B" in SP500_TICKERS and "BF B" in SP500_TICKERS
    assert not any("-" in t or "." in t for t in SP500_TICKERS)


def test_contains_well_known_members():
    assert {"AAPL", "MSFT", "NVDA", "MU", "JPM"} <= set(SP500_TICKERS)
