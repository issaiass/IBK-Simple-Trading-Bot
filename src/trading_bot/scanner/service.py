"""Scan orchestration: fetch, filter by rules.json thresholds, write the watchlist."""
import time
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path

from trading_bot.scanner.gappers import Gapper, Snapshot, select_gappers
from trading_bot.scanner.watchlist import write_watchlist
from trading_bot.timeutil import now_et


def run_scan(
    symbols: list[str],
    rules: dict,
    fetch: Callable[[list[str], date], list[Snapshot]],
    watchlist_path: Path,
    clock: Callable[[], datetime] = now_et,
) -> list[Gapper]:
    """One scan. If `fetch` raises, the previous watchlist is left untouched."""
    snapshots = fetch(symbols, clock().date())
    gappers = select_gappers(
        snapshots,
        min_gap_pct=rules["daily_filters"]["D3_min_gap_pct_from_prior_close"],
        min_price=rules["universe_filters"]["min_price_usd"],
    )
    write_watchlist(watchlist_path, gappers)
    return gappers


def scan_loop(
    scan: Callable[[], object],
    interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    iterations: int | None = None,
    on_error: Callable[[Exception], None] = print,
) -> None:
    """Run `scan` repeatedly; a failed scan is reported and the loop continues."""
    done = 0
    while iterations is None or done < iterations:
        try:
            scan()
        except Exception as exc:
            on_error(exc)
        done += 1
        if iterations is None or done < iterations:
            sleep(interval_seconds)
