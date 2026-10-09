"""CLI: BUY 1 share of MU with a protective stop.

Examples:
    buy-stop percent 2          stop 2% below entry
    buy-stop amount 15          stop $15 below entry
    buy-stop trail-amount 10    trailing stop $10 behind price
    buy-stop trail-percent 1.5  trailing stop 1.5% behind price
"""
import argparse
import sys

from trading_bot.broker.connection import connected, setup_logging
from trading_bot.broker.orders import buy_with_stop
from trading_bot.broker.stops import AmountStop, PercentStop, TrailingStop

CLIENT_ID = 12
BUILDERS = {
    "percent": lambda v: PercentStop(v),
    "amount": lambda v: AmountStop(v),
    "trail-amount": lambda v: TrailingStop(amount=v),
    "trail-percent": lambda v: TrailingStop(percent=v),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("kind", choices=BUILDERS)
    parser.add_argument("value", type=float)
    parser.add_argument("--symbol", default="MU")
    parser.add_argument("--quantity", type=float, default=1)
    args = parser.parse_args(argv)

    log = setup_logging("buy_with_stop")
    try:
        stop = BUILDERS[args.kind](args.value)
        with connected(CLIENT_ID) as ib:
            result = buy_with_stop(ib, args.symbol, args.quantity, stop)
    except Exception as exc:
        log.exception("buy with stop failed")
        print(f"Error: {exc!r}", file=sys.stderr)
        return 1

    entry = result.entry
    print(f"Entry order ID: {entry.order_id} status: {entry.status}")
    print(f"Stop order ID: {result.stop_order_id} type: {result.stop_type}")
    print(f"Stop price: {result.stop_price if result.stop_price else 'trailing'}")
    return 1 if entry.failed else 0


if __name__ == "__main__":
    sys.exit(main())
