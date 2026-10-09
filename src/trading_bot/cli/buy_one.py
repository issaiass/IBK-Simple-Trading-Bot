"""CLI: BUY 1 share of MU on the paper account."""
import sys

from trading_bot.broker.connection import connected, setup_logging
from trading_bot.broker.orders import buy_market

CLIENT_ID = 10


def main() -> int:
    log = setup_logging("buy_one")
    try:
        with connected(CLIENT_ID) as ib:
            result = buy_market(ib, "MU", 1)
    except Exception as exc:
        log.exception("buy failed")
        print(f"Error: {exc!r}", file=sys.stderr)
        return 1

    print(f"Order ID: {result.order_id}")
    print(f"Fill price: {result.fill_price if result.fill_price else 'pending'}")
    print(f"Status: {result.status}")
    if result.failed:
        for message in result.messages:
            print(f"trade.log: {message}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
