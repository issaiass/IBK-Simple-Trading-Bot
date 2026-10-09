"""One trading cycle: stop-outs, management, force-close, then the entry scan."""
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from trading_bot.cycle.decision_log import DecisionLog
from trading_bot.cycle.filters import FilterResult, evaluate_filters
from trading_bot.cycle.manage import Management, manage_position
from trading_bot.cycle.positions import STATE_PRE_BREAKEVEN, Position, PositionStore
from trading_bot.cycle.timegate import INACTIVE, time_gate
from trading_bot.notify import notify as default_notify
from trading_bot.notify import send_safely
from trading_bot.scanner.watchlist import read_watchlist
from trading_bot.settings import Settings
from trading_bot.sizing import initial_stop, risk_based_size
from trading_bot.trade import place_and_record
from trading_bot.trades_log import TradeLog

STOP_FILL_LOOKBACK = timedelta(hours=1)


@dataclass
class CycleContext:
    settings: Settings
    rules: dict
    broker: Any  # IBKRClient-like: orders, stops, positions, executions
    market_data: Any  # entry_inputs(symbol), position_snapshot(symbol, today)
    store: PositionStore
    trades: TradeLog
    log: DecisionLog
    watchlist_path: Path
    clock: Callable[[], datetime]
    runner: Callable[[str, str, int], subprocess.CompletedProcess]
    evaluate: Callable[..., FilterResult] = evaluate_filters
    notify: Callable[[str, str, str], None] = default_notify


def _alert(ctx: CycleContext, title: str, body: str, priority: str = "default") -> None:
    """Push notification; a failure here can never touch trading logic."""
    send_safely(ctx.notify, title, body, priority)


def _whole(qty: float) -> float:
    return int(qty) if qty == int(qty) else qty  # 28.0 -> 28


def _last_fill_price(ctx: CycleContext, symbol: str, side: str) -> float | None:
    last = ctx.trades.last_row()
    if last and last["symbol"] == symbol and last["side"] == side:
        return float(last["fill_price"]) or None
    return None


def run_cycle(ctx: CycleContext) -> str:
    """Run one cycle and return the time-gate status it ran under."""
    now = ctx.clock()
    status = time_gate(now, ctx.rules)
    if status in INACTIVE:
        return status
    ctx.log.record("cycle", status=status)  # heartbeat: the dashboard's "last cycle"

    positions = _drop_closed(ctx, ctx.store.load(), now)
    _flag_untracked(ctx, positions)
    if status == "force_close":
        ctx.store.save(_force_close(ctx, positions))
        return status

    _manage_all(ctx, positions, now)
    ctx.store.save(positions)
    if status == "ok":
        _scan_entries(ctx, positions, now)
    return status


def _sell(ctx: CycleContext, symbol: str, qty: float) -> bool:
    return place_and_record(ctx.broker, symbol, "SELL", _whole(qty), ctx.trades, lambda m: None) == 0


def _drop_closed(ctx: CycleContext, positions: list[Position], now: datetime) -> list[Position]:
    """Remove positions whose stop filled (matched by order id) or that are gone."""
    if not positions:
        return positions
    stopped = ctx.broker.stop_fill_prices(now - STOP_FILL_LOOKBACK)  # order id -> price
    held = ctx.broker.held_positions()
    kept = []
    for p in positions:
        if p.stop_order_id in stopped:
            exit_price = stopped[p.stop_order_id]
            pnl = (exit_price - p.entry_price) * p.qty
            ctx.log.record("stopped_out", symbol=p.symbol, stop_order_id=p.stop_order_id,
                           exit_price=exit_price, pnl=pnl)
            _alert(ctx, f"STOP {p.symbol}", f"exit ${exit_price:.2f}, P&L ${pnl:+.2f}")
        elif held.get(p.symbol, 0) <= 0:
            ctx.log.record("position_missing", symbol=p.symbol)
        else:
            kept.append(p)
    return kept


def _flag_untracked(ctx: CycleContext, positions: list[Position]) -> None:
    """Shout about broker positions the state file doesn't know (so have no stop)."""
    tracked = {p.symbol for p in positions}
    for symbol, qty in ctx.broker.held_positions().items():
        if symbol not in tracked:
            ctx.log.record("untracked_position", symbol=symbol, qty=qty, critical=True)


def _manage_all(ctx: CycleContext, positions: list[Position], now: datetime) -> None:
    for p in positions:
        try:
            price, lows = ctx.market_data.position_snapshot(p.symbol, now.date())
        except Exception as exc:
            ctx.log.record("manage_skipped", symbol=p.symbol, error=repr(exc))
            continue
        decision = manage_position(p, price, lows, ctx.rules["exit"])
        if decision:
            _apply(ctx, p, decision, price)


def _restore_stop(ctx: CycleContext, p: Position, price: float, qty: float) -> None:
    try:
        p.stop_order_id = ctx.broker.place_stop(p.symbol, qty, price)
        ctx.log.record("stop_restored", symbol=p.symbol, stop=price, qty=qty)
    except Exception as exc:
        ctx.log.record("stop_restore_failed", symbol=p.symbol, error=repr(exc), critical=True)


def _apply(ctx: CycleContext, p: Position, m: Management, price: float) -> None:
    """Cancel the old stop, sell any partial, place the new stop. Never leave a gap."""
    old_stop, old_state, old_qty = p.stop_price, p.state, p.qty
    ctx.broker.cancel_order_id(p.stop_order_id)

    if m.sell_qty:
        try:
            sold = _sell(ctx, p.symbol, m.sell_qty)
        except Exception as exc:
            sold, error = False, repr(exc)
        else:
            error = "sell rejected"
        if not sold:
            ctx.log.record("partial_failed", symbol=p.symbol, qty=m.sell_qty, error=error)
            _restore_stop(ctx, p, old_stop, p.qty)
            return
        ctx.log.record("partial_sold", symbol=p.symbol, qty=m.sell_qty, price=price)
        sold_at = _last_fill_price(ctx, p.symbol, "SELL") or price
        _alert(ctx, f"PARTIAL {p.symbol}",
               f"sold {_whole(m.sell_qty)}/{_whole(old_qty)} @ ${sold_at:.2f}")
        p.qty, p.state = m.new_qty, m.new_state

    try:
        new_id = ctx.broker.place_stop(p.symbol, m.new_qty, m.new_stop_price)
    except Exception as exc:
        ctx.log.record("stop_move_failed", symbol=p.symbol, error=repr(exc))
        _restore_stop(ctx, p, old_stop, p.qty)
        return

    p.stop_order_id, p.stop_price, p.state, p.qty = new_id, m.new_stop_price, m.new_state, m.new_qty
    event = "breakeven_stop" if old_state != m.new_state and not m.sell_qty else "stop_moved"
    ctx.log.record(event, symbol=p.symbol, old_stop=old_stop, new_stop=m.new_stop_price, price=price)
    if m.sell_qty:
        return  # the partial-profit alert already covered this move
    if old_state != m.new_state:
        _alert(ctx, f"BE {p.symbol}", f"stop -> ${m.new_stop_price:.2f}")
    else:
        _alert(ctx, f"TRAIL {p.symbol}", f"stop ${old_stop:.2f} -> ${m.new_stop_price:.2f}")


def _force_close(ctx: CycleContext, positions: list[Position]) -> list[Position]:
    """Cancel every stop and market-sell what is actually held. Returns leftovers."""
    held = ctx.broker.held_positions()
    leftovers = []
    if positions:
        _alert(ctx, "EOD Force Close", f"flattening {len(positions)} positions", "high")
    for p in positions:
        try:
            ctx.broker.cancel_order_id(p.stop_order_id)
            qty = held.get(p.symbol, 0)
            if qty > 0 and not _sell(ctx, p.symbol, qty):
                raise RuntimeError("sell rejected")
            ctx.log.record("force_close", symbol=p.symbol, qty=qty)
        except Exception as exc:
            ctx.log.record("force_close_failed", symbol=p.symbol, error=repr(exc), critical=True)
            leftovers.append(p)
    return leftovers


def _scan_entries(ctx: CycleContext, positions: list[Position], now: datetime) -> None:
    max_trades = ctx.settings.max_trades_per_day
    max_positions = ctx.rules["risk"]["max_concurrent_positions"]
    buys_today = ctx.trades.count_buys_on(now.date())

    # positions() FIRST: a tracked symbol we already hold must never be re-entered
    held = ctx.broker.held_positions()
    tracked = {p.symbol for p in positions}

    for symbol in read_watchlist(ctx.watchlist_path):
        if buys_today >= max_trades:
            ctx.log.record("max_trades_reached", count=buys_today)
            return
        if len(positions) >= max_positions:
            ctx.log.record("max_positions_reached", count=len(positions))
            return
        if symbol in held or symbol in tracked:
            ctx.log.record("entry_skipped", symbol=symbol, reasons=["already in position"])
            continue

        try:
            daily, intraday = ctx.market_data.entry_inputs(symbol)
            result = ctx.evaluate(daily, intraday, ctx.rules, now)
        except Exception as exc:
            ctx.log.record("entry_error", symbol=symbol, error=repr(exc))
            continue
        if not result.passed:
            ctx.log.record("entry_skipped", symbol=symbol, reasons=result.reasons,
                           checks=result.checks)
            continue

        stop = initial_stop(result.low_of_day)
        size = risk_based_size(
            result.price, stop, ctx.settings.portfolio_value_usd,
            ctx.settings.max_risk_per_trade_pct,
            ctx.rules["risk"]["max_position_size_pct_of_portfolio"],
        )
        if size < 1:
            ctx.log.record("entry_skipped", symbol=symbol, reasons=["size < 1"],
                           price=result.price, stop=stop)
            continue

        position = _enter(ctx, symbol, result, stop, size, now)
        if position:
            positions.append(position)
            tracked.add(symbol)
            buys_today += 1
            ctx.store.save(positions)  # persist immediately; a crash must not lose it


def _enter(
    ctx: CycleContext, symbol: str, result: FilterResult, stop: float, size: int, now: datetime
) -> Position | None:
    try:
        ctx.runner(symbol, "BUY", size)
    except subprocess.TimeoutExpired:
        ctx.log.record("entry_trade_timeout", symbol=symbol)
    except Exception as exc:
        ctx.log.record("entry_trade_error", symbol=symbol, error=repr(exc))

    # the broker, not the subprocess exit code, is the source of truth; poll because
    # a fill made by the trade process can take a moment to show up
    qty = ctx.broker.wait_for_position(symbol)
    if qty <= 0:
        ctx.log.record("entry_failed", symbol=symbol, size=size, critical=True,
                       note="no position seen; check TWS for a late fill")
        return None

    try:
        stop_id = ctx.broker.place_stop(symbol, qty, stop)
    except Exception as exc:
        ctx.log.record("entry_aborted_unprotected", symbol=symbol, error=repr(exc))
        if _sell_back(ctx, symbol, qty):
            return None
        stop_id = 0  # keep tracking it so the 15:51 force-close still sells it

    entry_price = _fill_price(ctx, symbol, result.price)
    ctx.log.record("entered", symbol=symbol, qty=qty, entry_price=entry_price, stop=stop,
                   R=entry_price - stop, stop_order_id=stop_id)
    _alert(ctx, f"BUY {symbol}", f"@ ${entry_price:.2f}, stop ${stop:.2f}, qty {_whole(qty)}")
    return Position(
        symbol=symbol, entry_price=entry_price,
        entry_time_iso=now.astimezone(timezone.utc).isoformat(), qty=qty,
        initial_stop=stop, stop_order_id=stop_id, state=STATE_PRE_BREAKEVEN,
        R=entry_price - stop,
    )


def _sell_back(ctx: CycleContext, symbol: str, qty: float) -> bool:
    try:
        if _sell(ctx, symbol, qty):
            return True
    except Exception as exc:
        ctx.log.record("sell_back_error", symbol=symbol, error=repr(exc))
    ctx.log.record("unprotected_position", symbol=symbol, qty=qty, critical=True)
    return False


def _fill_price(ctx: CycleContext, symbol: str, fallback: float) -> float:
    last = ctx.trades.last_row()
    if last and last["symbol"] == symbol and last["side"] == "BUY":
        price = float(last["fill_price"])
        if price > 0:
            return price
    return fallback
