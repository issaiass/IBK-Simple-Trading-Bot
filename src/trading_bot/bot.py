"""Orchestrator: guard, daily cap, evaluate, size, then spawn the executor."""
import argparse
import subprocess
import sys
from collections.abc import Callable
from datetime import datetime

from trading_bot.broker.client import IBKRClient
from trading_bot.config import PROJECT_ROOT, TRADES_CSV, load_rules
from trading_bot.settings import SafetyError, Settings, check_mode_matches_port
from trading_bot.sizing import position_size
from trading_bot.strategy import evaluate
from trading_bot.timeutil import now_et, stamp
from trading_bot.trades_log import TradeLog

TRADE_TIMEOUT_SECONDS = 30
FAILED_STATUSES = {"Cancelled", "ApiCancelled", "Inactive"}


def run_trade_process(symbol: str, side: str, size: int) -> subprocess.CompletedProcess:
    """Run the executor as a separate process; killed after 30s."""
    return subprocess.run(
        [sys.executable, "-m", "trading_bot.trade",
         "--symbol", symbol, "--side", side, "--size", str(size)],
        capture_output=True, text=True, timeout=TRADE_TIMEOUT_SECONDS, cwd=PROJECT_ROOT,
    )


def run(
    symbol: str,
    check_only: bool,
    settings: Settings,
    rules: dict,
    *,
    trades: TradeLog,
    clock: Callable[[], datetime] = now_et,
    client_factory: Callable = IBKRClient,
    evaluator: Callable = evaluate,
    runner: Callable = run_trade_process,
    out: Callable[[str], None] = print,
) -> int:
    """Run one evaluation/trade cycle. Returns a process exit code."""

    def say(message: str) -> None:
        out(stamp(message, clock()))

    check_mode_matches_port(settings)

    buys_today = trades.count_buys_on(clock().date())
    if buys_today >= settings.max_trades_per_day:
        say(f"Max trades per day reached ({buys_today}/{settings.max_trades_per_day}). Done.")
        return 0

    try:
        client = client_factory(settings.host, settings.port, settings.client_id, settings.paper_trading)
    except SafetyError:
        raise
    except Exception as exc:
        say(f"Connection failed: {exc!r}")
        return 1

    try:
        result = evaluator(symbol, client.ib)
        say(f"Evaluation: {result}")
        if check_only:
            return 0
        if not result["pass"]:
            say(f"No trade: {'; '.join(result['reasons'])}")
            return 0

        quantity = position_size(
            result["price"],
            settings.max_trade_size_usd,
            settings.portfolio_value_usd,
            rules["risk"]["max_position_size_pct_of_portfolio"],
        )
        if quantity < 1:
            say("position too small")
            return 0

        say(f"Placing BUY {quantity} {symbol} @ ~{result['price']}")
        try:
            completed = runner(symbol, "BUY", quantity)
        except subprocess.TimeoutExpired:
            say(f"Trade process exceeded {TRADE_TIMEOUT_SECONDS}s and was killed")
            return 1
        for line in (completed.stdout or "").splitlines():
            say(line)

        last = trades.last_row()
        if last and last["status"] not in FAILED_STATUSES and completed.returncode == 0:
            say(f"Trade success: {last['side']} {last['size']} {last['symbol']} ({last['status']})")
            return 0
        say(f"Trade failed (exit code {completed.returncode}). {completed.stderr or ''}".strip())
        return 1
    finally:
        client.disconnect()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Single-symbol trading bot (paper)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    try:
        return run(
            args.symbol, args.check_only, settings, load_rules(),
            trades=TradeLog(TRADES_CSV),
        )
    except SafetyError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    sys.exit(main())
