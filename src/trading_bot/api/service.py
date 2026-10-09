"""Builds the dashboard payload from the bot's files (trades, positions, decision log)."""
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from trading_bot.api.schemas import (
    ActionData,
    CycleData,
    DashboardData,
    EquityPoint,
    OpenPositionData,
    PaperProgressData,
    SkipData,
    StatusData,
    SummaryData,
    TradeData,
)
from trading_bot.api.sources import DecisionLogReader
from trading_bot.cycle.positions import Position, PositionStore
from trading_bot.reporting.performance import pair_trades, read_trades, summarize_range
from trading_bot.reporting.rmultiple import RTrade, attach_r, histogram
from trading_bot.timeutil import ET

ACTIVE_WITHIN_MINUTES = 10  # the cycle runs every 5 minutes, so one missed run is still active
RECENT_TRADES = 20
MAX_SKIPS_SHOWN = 10
PAPER_TARGET_DAYS = 14  # the recommended minimum paper run before risking anything real

#: period -> how many calendar days it spans, today included (None: no lower bound)
PERIOD_DAYS: dict[str, int | None] = {"today": 1, "7d": 7, "30d": 30, "all": None}

#: events that mean the bot changed something this cycle
ACTION_EVENTS = {
    "entered", "partial_sold", "breakeven_stop", "stop_moved", "stopped_out", "force_close",
    "stop_restored",
}


class InvalidPeriod(ValueError):
    """The requested period is not one of PERIOD_DAYS."""


class PriceProvider(Protocol):
    def latest(self, symbols: list[str]) -> dict[str, float]: ...


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _is_error(event: dict) -> bool:
    name = str(event.get("event", ""))
    return bool(event.get("critical")) or name.endswith(("_failed", "_error"))


def _first_trade_date(rows: list[dict]) -> date | None:
    dates = []
    for row in rows:
        try:
            dates.append(datetime.fromisoformat(row["timestamp_iso"]).astimezone(ET).date())
        except (KeyError, ValueError, TypeError):
            continue
    return min(dates, default=None)


class DashboardService:
    def __init__(
        self,
        *,
        trades_path: Path,
        positions: PositionStore,
        decision_log: DecisionLogReader,
        prices: PriceProvider,
        clock: Callable[[], datetime],
        gate: Callable[[datetime], str],
        paper_mode: bool = True,
        recent_limit: int = RECENT_TRADES,
    ):
        self._trades_path = trades_path
        self._positions = positions
        self._log = decision_log
        self._prices = prices
        self._clock = clock
        self._gate = gate
        self._paper_mode = paper_mode
        self._recent_limit = recent_limit

    def dashboard(self, period: str = "today") -> DashboardData:
        if period not in PERIOD_DAYS:
            raise InvalidPeriod(period)
        now = self._clock()
        warnings: list[str] = []
        today = now.astimezone(ET).date()
        start = self._period_start(period, today)

        rows = read_trades(self._trades_path)
        closed, _ = pair_trades(rows)
        in_period = [t for t in closed if start is None or t.closed.date() >= start]
        r_trades = attach_r(in_period, self._log.entered_stops())
        by_close = sorted(r_trades, key=lambda r: r.trade.closed)

        return DashboardData(
            generated_at=now.isoformat(),
            period=period,
            status=self._status(now),
            summary=self._summary(closed, start, today),
            paper=self._paper_progress(rows, today),
            cycle=self._cycle(),
            r_histogram=histogram(r.r_multiple for r in r_trades),
            open_positions=self._open_positions(warnings, now),
            recent_trades=[self._trade(r) for r in reversed(by_close)][: self._recent_limit],
            equity_curve=self._equity_curve(by_close),
            warnings=warnings,
        )

    def _paper_progress(self, rows: list[dict], today: date) -> PaperProgressData:
        first = _first_trade_date(rows)
        days = 0 if first is None else (today - first).days + 1
        return PaperProgressData(
            paper_mode=self._paper_mode,
            first_trade_date=None if first is None else first.isoformat(),
            days_traded=days,
            target_days=PAPER_TARGET_DAYS,
            days_remaining=max(0, PAPER_TARGET_DAYS - days),
            reached=days >= PAPER_TARGET_DAYS,
        )

    @staticmethod
    def _period_start(period: str, today: date) -> date | None:
        days = PERIOD_DAYS[period]
        return None if days is None else today - timedelta(days=days - 1)

    @staticmethod
    def _summary(closed, start: date | None, today: date) -> SummaryData:
        s = summarize_range(closed, start, today)
        return SummaryData(
            from_date=s["from_date"], to_date=s["to_date"], total_trades=s["total_trades"],
            wins=s["wins"], losses=s["losses"], breakeven=s["breakeven"],
            win_rate_pct=s["win_rate_pct"], gross_pnl_usd=s["gross_pnl_usd"],
            profit_factor=s["profit_factor"], largest_winner=s["largest_winner"],
            largest_loser=s["largest_loser"], avg_winner=s["avg_winner"], avg_loser=s["avg_loser"],
        )

    @staticmethod
    def _trade(r: RTrade) -> TradeData:
        t = r.trade
        return TradeData(
            symbol=t.symbol, qty=t.qty, entry_price=round(t.entry_price, 4),
            exit_price=round(t.exit_price, 4), pnl_usd=round(t.pnl_usd, 2),
            pnl_pct=round(t.pnl_pct, 2), r_multiple=_round(r.r_multiple), r_source=r.r_source,
            opened_at=t.opened.isoformat(), closed_at=t.closed.isoformat(),
            hold_minutes=round(t.hold_minutes, 1),
        )

    @staticmethod
    def _equity_curve(by_close: list[RTrade]) -> list[EquityPoint]:
        total, points = 0.0, []
        for r in by_close:
            pnl = round(r.trade.pnl_usd, 2)
            total = round(total + pnl, 2)
            points.append(EquityPoint(r.trade.closed.isoformat(), r.trade.symbol, pnl, total))
        return points

    def _open_positions(self, warnings: list[str], now: datetime) -> list[OpenPositionData]:
        try:
            positions = self._positions.load()
        except ValueError as exc:
            warnings.append(f"open_positions.json is unreadable: {exc}")
            return []
        if not positions:
            return []
        try:
            prices = self._prices.latest([p.symbol for p in positions])
        except Exception as exc:
            warnings.append(f"live prices unavailable: {exc}")
            prices = {}
        return [self._position(p, prices.get(p.symbol), now) for p in positions]

    @staticmethod
    def _position(p: Position, price: float | None, now: datetime) -> OpenPositionData:
        unrealized_r = unrealized_pnl = stop_distance = target_distance = None
        target = round(p.entry_price + p.R, 4)
        if price is not None:
            unrealized_pnl = round((price - p.entry_price) * p.qty, 2)
            if p.R > 0:
                unrealized_r = round((price - p.entry_price) / p.R, 2)
            stop_distance = round((price - p.stop_price) / price * 100, 2)
            target_distance = round((target - price) / price * 100, 2)
        try:
            hold = round((now - datetime.fromisoformat(p.entry_time_iso)).total_seconds() / 60, 1)
        except (ValueError, TypeError):
            hold = None
        return OpenPositionData(
            symbol=p.symbol, qty=p.qty, entry_price=p.entry_price, stop_price=p.stop_price,
            initial_stop=p.initial_stop, state=p.state, current_price=price,
            unrealized_r=unrealized_r, unrealized_pnl_usd=unrealized_pnl,
            opened_at=p.entry_time_iso, hold_minutes=hold, target_price=target,
            stop_distance_pct=stop_distance, target_distance_pct=target_distance,
        )

    def _cycle(self) -> CycleData | None:
        heartbeat, events = self._log.last_cycle_events()
        if heartbeat is None:
            return None
        skips = [e for e in events if e.get("event") == "entry_skipped"]
        return CycleData(
            at=str(heartbeat.get("timestamp", "")),
            gate=str(heartbeat.get("status", "")),
            entries=sum(1 for e in events if e.get("event") == "entered"),
            skipped=len(skips),
            skips=[
                SkipData(str(e.get("symbol", "")), [str(r) for r in e.get("reasons") or []])
                for e in skips[:MAX_SKIPS_SHOWN]
            ],
            actions=[self._action(e) for e in events if e.get("event") in ACTION_EVENTS],
            errors=[self._action(e) for e in events if _is_error(e)],
        )

    @staticmethod
    def _action(event: dict) -> ActionData:
        symbol = event.get("symbol")
        return ActionData(str(event.get("event")), None if symbol is None else str(symbol))

    def _status(self, now: datetime) -> StatusData:
        last = self._log.last_event()
        heartbeat = self._log.last_cycle()
        last_event = last.get("event") if last else None
        gate = self._gate(now)
        if heartbeat is None:
            return StatusData("NO_DATA", None, last_event, "no cycle data yet", gate)
        try:
            age = max(0.0, (now - datetime.fromisoformat(heartbeat["timestamp"])).total_seconds() / 60)
        except (KeyError, ValueError, TypeError):
            return StatusData("NO_DATA", None, last_event, "no cycle data yet", gate)
        active = age <= ACTIVE_WITHIN_MINUTES
        return StatusData(
            "ACTIVE" if active else "IDLE", heartbeat["timestamp"], last_event,
            f"last cycle {int(age)} min ago", gate,
        )
