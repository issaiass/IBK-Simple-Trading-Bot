"""Connection settings and helper for Interactive Brokers TWS."""
import logging
from contextlib import contextmanager

from ib_async import IB

from trading_bot.config import LOG_DIR

HOST, PORT = "127.0.0.1", 7497  # paper trading


def setup_logging(name: str) -> logging.Logger:
    LOG_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOG_DIR / "trade.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return logging.getLogger(name)


@contextmanager
def connected(client_id: int, host: str = HOST, port: int = PORT):
    """Connect to TWS and always disconnect on exit."""
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id)
        yield ib
    finally:
        ib.disconnect()
