"""CLI: scan the S&P 500 for gappers and refresh watchlist.txt.

    scan                run once
    scan --loop         rescan every 30 minutes (Ctrl+C to stop)
"""
import argparse
import sys

from trading_bot.config import WATCHLIST_PATH, load_rules
from trading_bot.scanner.service import run_scan, scan_loop
from trading_bot.scanner.yahoo import fetch_snapshots
from trading_bot.sp500_tickers import SP500_TICKERS
from trading_bot.timeutil import now_et, stamp


def say(message: str) -> None:
    print(stamp(message, now_et()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S&P 500 gapper scanner")
    parser.add_argument("--loop", action="store_true", help="keep rescanning")
    parser.add_argument("--interval-minutes", type=float, default=30)
    args = parser.parse_args(argv)

    rules = load_rules()

    def scan() -> None:
        gappers = run_scan(SP500_TICKERS, rules, fetch_snapshots, WATCHLIST_PATH)
        say(f"{len(gappers)} gappers written to {WATCHLIST_PATH.name}")
        for g in gappers:
            say(f"  {g.symbol:<6} {g.gap_pct:+6.2f}%  {g.prior_close:.2f} -> {g.price:.2f}")

    if not args.loop:
        scan()
        return 0
    try:
        scan_loop(scan, args.interval_minutes * 60, on_error=lambda e: say(f"Scan failed: {e!r}"))
    except KeyboardInterrupt:
        say("Stopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
