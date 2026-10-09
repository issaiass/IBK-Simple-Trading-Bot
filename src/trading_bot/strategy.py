"""Entry evaluation for a single symbol.

Only the position dedupe and the time gate live here. The daily/intraday
filters (D1-D3, I1-I3) are built in a later chapter.
"""
import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ib_async import IB, Stock

from trading_bot.broker.orders import reference_price
from trading_bot.config import SAFETY_LOG, load_rules
from trading_bot.timeutil import now_et, parse_hhmm


def _market_price(ib: IB, symbol: str) -> float:
    return reference_price(ib, Stock(symbol, "SMART", "USD"))


def _result(passed: bool, reasons: list[str], price: float) -> dict:
    return {"pass": bool(passed), "reasons": reasons, "price": float(price)}


def _log(symbol: str, now: datetime, result: dict, log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"timestamp": now.isoformat(), "symbol": symbol, **result}
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def evaluate(
    symbol: str,
    ib: IB,
    rules: dict | None = None,
    now: datetime | None = None,
    price_fn: Callable[[IB, str], float] = _market_price,
    log_path: Path | None = None,
) -> dict:
    """Return {"pass", "reasons", "price"} and append it to the safety log."""
    rules = rules if rules is not None else load_rules()
    now = now or now_et()
    window = rules["time_filter"]
    earliest, latest = window["earliest_entry_et"], window["latest_entry_et"]

    if any(p.contract.symbol == symbol and p.position > 0 for p in ib.positions()):
        result = _result(False, ["already in position"], 0.0)
    elif not parse_hhmm(earliest) <= now.time().replace(second=0, microsecond=0) <= parse_hhmm(latest):
        result = _result(False, [f"outside entry window {earliest}-{latest}"], 0.0)
    else:
        result = _result(
            True, ["time gate ok", "no existing position"], price_fn(ib, symbol)
        )

    _log(symbol, now, result, log_path or SAFETY_LOG)
    return result
