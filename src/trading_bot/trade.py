"""Executor process: places one order and records it in trades.csv.

Runs as its own process with IBKR_EXEC_CLIENT_ID so it never fights the
orchestrator (bot.py) over the TWS connection.
"""
import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timezone

from trading_bot.broker.client import IBKRClient
from trading_bot.config import TRADES_CSV
from trading_bot.settings import SafetyError, Settings, check_mode_matches_port
from trading_bot.trades_log import TradeLog, TradeLogLocked

REJECTED = {"Cancelled", "ApiCancelled", "Inactive"}


def place_and_record(
    client: IBKRClient,
    symbol: str,
    side: str,
    size: float,
    trades: TradeLog,
    out: Callable[[str], None],
) -> int:
    """Place an order, wait for the fill, and append the real result to the CSV."""
    trade = client.place_order(symbol, side, size)
    client.wait_for_fill(trade)
    status = trade.orderStatus.status
    if status in REJECTED:
        out(f"Order {status}:")
        for entry in trade.log:
            out(f"  {entry.status} {entry.message}")
        return 1

    trades.append({
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "side": side,
        "size": size,
        "fill_price": trade.orderStatus.avgFillPrice or 0,
        "order_id": trade.order.orderId,
        "status": status,
    })
    out(f"{side} {size} {symbol}: {status} (order {trade.order.orderId})")
    return 0


def run_guarded(
    settings: Settings,
    action: Callable[[IBKRClient], int],
    client_factory: Callable,
    out: Callable[[str], None],
) -> int:
    """Connect with the executor client id, run `action`, always disconnect."""
    try:
        client = client_factory(settings.host, settings.port, settings.exec_client_id, settings.paper_trading)
    except SafetyError:
        raise
    except Exception as exc:
        out(f"Connection failed: {exc!r}")
        return 1

    try:
        return action(client)
    except TradeLogLocked as exc:
        out(f"Could not record trade: {exc}")
        return 1
    except Exception as exc:
        out(f"Order failed: {exc!r}")
        return 1
    finally:
        client.disconnect()


def execute(
    symbol: str,
    side: str,
    size: int,
    settings: Settings,
    trades: TradeLog,
    client_factory: Callable = IBKRClient,
    out: Callable[[str], None] = print,
) -> int:
    """Place the order and log it. Returns a process exit code."""
    return run_guarded(
        settings,
        lambda client: place_and_record(client, symbol, side, size, trades, out),
        client_factory,
        out,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Place one order (paper trading)")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--side", required=True, choices=["BUY", "SELL"])
    parser.add_argument("--size", required=True, type=int)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    try:
        check_mode_matches_port(settings)
    except SafetyError as exc:
        sys.exit(str(exc))
    try:
        return execute(args.symbol, args.side, args.size, settings, TradeLog(TRADES_CSV))
    except SafetyError as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    sys.exit(main())
