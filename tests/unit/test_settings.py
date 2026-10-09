import pytest

from trading_bot.settings import (
    SafetyError,
    Settings,
    check_account_matches_mode,
    check_mode_matches_port,
)

ENV = {
    "IBKR_HOST": "127.0.0.1",
    "IBKR_PORT": "7497",
    "IBKR_CLIENT_ID": "2",
    "IBKR_EXEC_CLIENT_ID": "3",
    "PAPER_TRADING": "true",
    "PORTFOLIO_VALUE_USD": "25000",
    "MAX_TRADE_SIZE_USD": "2500",
    "MAX_TRADES_PER_DAY": "5",
    "MAX_RISK_PER_TRADE_PCT": "1.0",
}


def test_parses_environment():
    s = Settings.from_env(ENV)
    assert (s.host, s.port, s.client_id, s.exec_client_id) == ("127.0.0.1", 7497, 2, 3)
    assert s.paper_trading is True
    assert s.portfolio_value_usd == 25000
    assert s.max_trade_size_usd == 2500
    assert s.max_trades_per_day == 5
    assert s.max_risk_per_trade_pct == 1.0


@pytest.mark.parametrize("raw, expected", [("true", True), ("TRUE", True), ("false", False), ("False", False)])
def test_paper_flag_parsing(raw, expected):
    assert Settings.from_env({**ENV, "PAPER_TRADING": raw}).paper_trading is expected


def test_missing_key_raises_clear_error():
    env = {k: v for k, v in ENV.items() if k != "IBKR_PORT"}
    with pytest.raises(KeyError, match="IBKR_PORT"):
        Settings.from_env(env)


def test_orchestrator_and_executor_need_different_client_ids():
    with pytest.raises(ValueError, match="client"):
        Settings.from_env({**ENV, "IBKR_EXEC_CLIENT_ID": "2"})


@pytest.mark.parametrize("port", [7496, 4001])
def test_paper_flag_with_live_port_aborts(port):
    s = Settings.from_env({**ENV, "IBKR_PORT": str(port)})
    with pytest.raises(SafetyError, match="paper flag but live port"):
        check_mode_matches_port(s)


@pytest.mark.parametrize("port", [7497, 4002])
def test_live_flag_with_paper_port_aborts(port):
    s = Settings.from_env({**ENV, "PAPER_TRADING": "false", "IBKR_PORT": str(port)})
    with pytest.raises(SafetyError, match="live flag but paper port"):
        check_mode_matches_port(s)


def test_matching_modes_pass():
    check_mode_matches_port(Settings.from_env(ENV))
    check_mode_matches_port(
        Settings.from_env({**ENV, "PAPER_TRADING": "false", "IBKR_PORT": "7496"})
    )


class TestAccountMatchesMode:
    """The port can lie (a Gateway on a custom port); the account id cannot."""

    def test_paper_flag_accepts_paper_accounts(self):
        check_account_matches_mode(True, ["DU1234567"])

    def test_live_flag_accepts_live_accounts(self):
        check_account_matches_mode(False, ["U1234567"])

    def test_paper_flag_rejects_a_live_account(self):
        with pytest.raises(SafetyError, match="paper flag but live account"):
            check_account_matches_mode(True, ["U1234567"])

    def test_live_flag_rejects_a_paper_account(self):
        with pytest.raises(SafetyError, match="live flag but paper account"):
            check_account_matches_mode(False, ["DU1234567"])

    def test_one_live_account_among_paper_ones_is_enough_to_abort(self):
        with pytest.raises(SafetyError):
            check_account_matches_mode(True, ["DU1234567", "U7654321"])

    def test_no_account_reported_aborts(self):
        with pytest.raises(SafetyError, match="no account"):
            check_account_matches_mode(True, [])
