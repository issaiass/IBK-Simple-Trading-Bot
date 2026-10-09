"""Environment-driven settings and the paper/live safety guard."""
import os
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

from trading_bot.config import PROJECT_ROOT

LIVE_PORTS = {7496, 4001}
PAPER_PORTS = {7497, 4002}


class SafetyError(Exception):
    """Raised when the paper/live flag contradicts the configured port."""


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    client_id: int
    exec_client_id: int
    paper_trading: bool
    portfolio_value_usd: float
    max_trade_size_usd: float
    max_trades_per_day: int
    max_risk_per_trade_pct: float

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        """Build from `env`, or from .env plus os.environ when omitted."""
        if env is None:
            load_dotenv(PROJECT_ROOT / ".env")
            env = os.environ
        settings = cls(
            host=env["IBKR_HOST"],
            port=int(env["IBKR_PORT"]),
            client_id=int(env["IBKR_CLIENT_ID"]),
            exec_client_id=int(env["IBKR_EXEC_CLIENT_ID"]),
            paper_trading=env["PAPER_TRADING"].strip().lower() == "true",
            portfolio_value_usd=float(env["PORTFOLIO_VALUE_USD"]),
            max_trade_size_usd=float(env["MAX_TRADE_SIZE_USD"]),
            max_trades_per_day=int(env["MAX_TRADES_PER_DAY"]),
            max_risk_per_trade_pct=float(env["MAX_RISK_PER_TRADE_PCT"]),
        )
        if settings.client_id == settings.exec_client_id:
            raise ValueError("orchestrator and executor need different client ids")
        return settings


def check_mode_matches_port(settings: Settings) -> None:
    if settings.paper_trading and settings.port in LIVE_PORTS:
        raise SafetyError("ABORT: paper flag but live port")
    if not settings.paper_trading and settings.port in PAPER_PORTS:
        raise SafetyError("ABORT: live flag but paper port")


def check_account_matches_mode(paper_trading: bool, accounts: list[str]) -> None:
    """IBKR paper account ids start with "D" (DU...); live ones do not."""
    if not accounts:
        raise SafetyError("ABORT: no account reported by the broker")
    has_paper = any(a.startswith("D") for a in accounts)
    has_live = any(not a.startswith("D") for a in accounts)
    if paper_trading and has_live:
        raise SafetyError("ABORT: paper flag but live account")
    if not paper_trading and has_paper:
        raise SafetyError("ABORT: live flag but paper account")
