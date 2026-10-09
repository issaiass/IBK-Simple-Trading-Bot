"""Run the dashboard API: `uv run serve-api` (localhost only by default)."""
import os
from collections.abc import Mapping
from dataclasses import dataclass

import uvicorn
from dotenv import load_dotenv

from trading_bot.api.app import create_app
from trading_bot.api.service import DashboardService
from trading_bot.api.sources import CachedPriceProvider, DecisionLogReader, yahoo_price
from trading_bot.config import DECISION_LOG_PATH, POSITIONS_PATH, PROJECT_ROOT, TRADES_CSV, load_rules
from trading_bot.cycle.timegate import time_gate
from trading_bot.cycle.positions import PositionStore
from trading_bot.timeutil import now_et

DEFAULT_HOST = "127.0.0.1"  # the data is financial: not reachable from the network by default
DEFAULT_PORT = 8000


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ApiSettings":
        raw_port = env.get("DASHBOARD_API_PORT", str(DEFAULT_PORT))
        try:
            port = int(raw_port)
        except ValueError:
            port = 0
        if not 1 <= port <= 65535:
            raise ValueError(f"DASHBOARD_API_PORT must be 1-65535, got {raw_port!r}")
        return cls(env.get("DASHBOARD_API_HOST", DEFAULT_HOST), port)


def paper_mode_from(env: Mapping[str, str]) -> bool:
    """PAPER_TRADING as the bot reads it; paper unless explicitly turned off."""
    return env.get("PAPER_TRADING", "true").strip().lower() != "false"


def build_service() -> DashboardService:
    """The real files and Yahoo prices. Nothing is read until a request arrives."""
    rules = load_rules()
    return DashboardService(
        trades_path=TRADES_CSV,
        positions=PositionStore(POSITIONS_PATH),
        decision_log=DecisionLogReader(DECISION_LOG_PATH),
        prices=CachedPriceProvider(yahoo_price),
        clock=now_et,
        gate=lambda now: time_gate(now, rules),
        paper_mode=paper_mode_from(os.environ),
    )


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    settings = ApiSettings.from_env(os.environ)
    uvicorn.run(create_app(build_service()), host=settings.host, port=settings.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
