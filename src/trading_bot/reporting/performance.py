"""Daily performance summary built from trades.csv (read-only).

A "trade" is one BUY entry closed by SELLs, matched FIFO by quantity. Partial
exits therefore belong to the same trade, and a trade counts for the day on
which its final SELL happened (Eastern time).
"""
import argparse
import csv
import json
import sys
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from trading_bot.config import TRADES_CSV
from trading_bot.notify import notify as default_notify
from trading_bot.notify import send_safely
from trading_bot.timeutil import ET, now_et


@dataclass(frozen=True)
class ClosedTrade:
    symbol: str
    qty: float
    entry_price: float
    exit_price: float  # average across partial exits
    pnl_usd: float
    pnl_pct: float
    hold_minutes: float  # entry to the final exit
    opened: datetime
    closed: datetime
    stop_price: float | None = None  # initial stop, when trades.csv has a stop_price column


def read_trades(path: Path) -> list[dict]:
    """Rows of trades.csv; a missing file means no trades (and is not created)."""
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _optional_price(value) -> float | None:
    """A positive float, or None for a missing/blank/garbled value."""
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if number > 0 else None


def _parse(row: dict):
    """(time_et, symbol, side, size, price, stop) or None if the row is unusable."""
    try:
        price, size = float(row["fill_price"]), float(row["size"])
        when = datetime.fromisoformat(row["timestamp_iso"]).astimezone(ET)
        side, symbol = row["side"], row["symbol"]
    except (KeyError, ValueError, TypeError):
        return None
    if price <= 0 or size <= 0 or side not in ("BUY", "SELL"):
        return None
    return when, symbol, side, size, price, _optional_price(row.get("stop_price"))


def pair_trades(rows: list[dict]) -> tuple[list[ClosedTrade], dict]:
    """FIFO-match SELLs to BUYs per symbol. Returns (closed trades, diagnostics)."""
    parsed, ignored = [], 0
    for row in rows:
        item = _parse(row)
        if item is None:
            ignored += 1
        else:
            parsed.append(item)
    parsed.sort(key=lambda item: item[0])

    lots: dict[str, deque] = defaultdict(deque)
    closed: list[ClosedTrade] = []
    unmatched = 0.0
    for when, symbol, side, size, price, stop in parsed:
        if side == "BUY":
            lots[symbol].append({"opened": when, "qty": size, "left": size,
                                 "entry": price, "proceeds": 0.0, "stop": stop})
            continue
        remaining = size
        while remaining > 1e-9 and lots[symbol]:
            lot = lots[symbol][0]
            take = min(remaining, lot["left"])
            lot["proceeds"] += take * price
            lot["left"] -= take
            remaining -= take
            if lot["left"] <= 1e-9:
                lots[symbol].popleft()
                cost = lot["qty"] * lot["entry"]
                pnl = lot["proceeds"] - cost
                closed.append(ClosedTrade(
                    symbol=symbol, qty=lot["qty"], entry_price=lot["entry"],
                    exit_price=lot["proceeds"] / lot["qty"], pnl_usd=pnl,
                    pnl_pct=pnl / cost * 100,
                    hold_minutes=(when - lot["opened"]).total_seconds() / 60,
                    opened=lot["opened"], closed=when, stop_price=lot["stop"],
                ))
        unmatched += remaining
    return closed, {"ignored_rows": ignored, "unmatched_sell_qty": unmatched}


def _detail(t: ClosedTrade) -> dict:
    return {
        "symbol": t.symbol, "qty": t.qty,
        "entry_price": round(t.entry_price, 4), "exit_price": round(t.exit_price, 4),
        "pnl_usd": round(t.pnl_usd, 2), "pnl_pct": round(t.pnl_pct, 2),
        "hold_minutes": round(t.hold_minutes, 1),
    }


def _profit_factor(win_sum: float, loss_sum: float, total: int):
    if total == 0:
        return "n/a"
    if loss_sum == 0:
        return "inf" if win_sum > 0 else "n/a"
    return round(win_sum / abs(loss_sum), 2)


def summarize(trades: list[ClosedTrade], day: date) -> dict:
    """Aggregate the trades whose final exit fell on `day` (Eastern time)."""
    summary = summarize_range(trades, day, day)
    return {"date": day.isoformat(), **summary}


def summarize_range(trades: list[ClosedTrade], start: date | None, end: date) -> dict:
    """Aggregate the trades that closed from `start` to `end`, both inclusive (None: no lower bound)."""
    todays = sorted(
        (t for t in trades if (start is None or t.closed.date() >= start) and t.closed.date() <= end),
        key=lambda t: t.closed,
    )
    pnls = [round(t.pnl_usd, 2) for t in todays]
    winners = [(t, p) for t, p in zip(todays, pnls) if p > 0]
    losers = [(t, p) for t, p in zip(todays, pnls) if p < 0]
    win_sum, loss_sum = sum(p for _, p in winners), sum(p for _, p in losers)
    total = len(todays)

    def extreme(pairs, pick):
        if not pairs:
            return None
        t, p = pick(pairs, key=lambda pair: pair[1])
        return {"symbol": t.symbol, "pnl_usd": p}

    return {
        "from_date": start.isoformat() if start else None,
        "to_date": end.isoformat(),
        "total_trades": total,
        "wins": len(winners),
        "losses": len(losers),
        "breakeven": total - len(winners) - len(losers),
        "win_rate_pct": round(len(winners) / total * 100, 1) if total else 0.0,
        "gross_pnl_usd": round(sum(pnls), 2),
        "largest_winner": extreme(winners, max),
        "largest_loser": extreme(losers, min),
        "avg_winner": round(win_sum / len(winners), 2) if winners else None,
        "avg_loser": round(loss_sum / len(losers), 2) if losers else None,
        "profit_factor": _profit_factor(win_sum, loss_sum, total),
        "trades": [_detail(t) for t in todays],
    }


def format_notification(summary: dict) -> tuple[str, str]:
    title = f"Daily Summary {summary['date']}"
    if summary["total_trades"] == 0:
        return title, "No closed trades today."
    best = max(summary["trades"], key=lambda t: t["pnl_usd"])
    worst = min(summary["trades"], key=lambda t: t["pnl_usd"])
    pf = summary["profit_factor"]
    pf_text = pf if isinstance(pf, str) else f"{pf:.2f}"
    body = (
        f"Trades: {summary['total_trades']} ({summary['wins']}W / {summary['losses']}L, "
        f"{summary['win_rate_pct']}%)\n"
        f"P&L: ${summary['gross_pnl_usd']:+.2f}\n"
        f"Best: {best['symbol']} ${best['pnl_usd']:+.2f}\n"
        f"Worst: {worst['symbol']} ${worst['pnl_usd']:+.2f}\n"
        f"PF: {pf_text}"
    )
    return title, body


def run(
    trades_path: Path,
    now: datetime,
    notify: Callable[[str, str, str], None] = default_notify,
    out: Callable[[str], None] = print,
    send: bool = True,
) -> int:
    """Print the JSON summary for `now`'s Eastern date and (optionally) push it."""
    closed, _ = pair_trades(read_trades(trades_path))
    summary = summarize(closed, now.astimezone(ET).date())
    out(json.dumps(summary))
    if send:
        title, body = format_notification(summary)
        send_safely(notify, title, body)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daily performance summary")
    parser.add_argument("--no-notify", action="store_true", help="print only; no Telegram")
    args = parser.parse_args(argv)
    return run(TRADES_CSV, now_et(), send=not args.no_notify)


if __name__ == "__main__":
    sys.exit(main())
