"""Close a long position and record the SELL in trades.csv."""
import argparse
import sys
from collections.abc import Callable

from trading_bot.broker.client import IBKRClient
from trading_bot.config import TRADES_CSV
from trading_bot.settings import SafetyError, Settings, check_mode_matches_port
from trading_bot.trade import place_and_record, run_guarded
from trading_bot.trades_log import TradeLog


def close(
    symbol: str,
    settings: Settings,
    trades: TradeLog,
    client_factory: Callable = IBKRClient,
    out: Callable[[str], None] = print,
) -> int:
    """Cancel working orders on `symbol`, then sell the whole long position."""

    def action(client: IBKRClient) -> int:
        client.cancel_open_orders(symbol)
        quantity = next(
            (
                p.position
                for p in client.ib.positions()
                if p.contract.symbol == symbol and p.position > 0
            ),
            0,
        )
        if not quantity:
            out("NO POSITION TO CLOSE")
            return 0
        size = int(quantity) if quantity == int(quantity) else quantity
        return place_and_record(client, symbol, "SELL", size, trades, out)

    return run_guarded(settings, action, client_factory, out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Close a long position (paper trading)")
    parser.add_argument("--symbol", required=True)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    try:
        check_mode_matches_port(settings)
    except SafetyError as exc:
        sys.exit(str(exc))
    return close(args.symbol, settings, TradeLog(TRADES_CSV))


if __name__ == "__main__":
    sys.exit(main())
