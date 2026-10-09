"""CLI: close the MU position on the paper account."""
import sys

from trading_bot.broker.connection import connected, setup_logging
from trading_bot.broker.orders import close_position

CLIENT_ID = 11


def main() -> int:
    log = setup_logging("close_one")
    try:
        with connected(CLIENT_ID) as ib:
            result = close_position(ib, "MU")
    except Exception as exc:
        log.exception("close failed")
        print(f"Error: {exc!r}", file=sys.stderr)
        return 1

    if result is None:
        print("NO POSITION TO CLOSE")
        return 0
    print(f"Sold quantity: {result.quantity}")
    print(f"Fill price: {result.fill_price if result.fill_price else 'pending'}")
    print(f"Status: {result.status}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
