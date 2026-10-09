"""The JSON contract of the dashboard API (mirrored by frontend/src/types/dashboard.ts)."""
from dataclasses import dataclass, field

from trading_bot.reporting.rmultiple import Bucket as RBucket  # re-exported as part of the contract

__all__ = [
    "ActionData", "CycleData", "DashboardData", "EquityPoint", "OpenPositionData", "RBucket",
    "SkipData", "StatusData", "SummaryData", "TradeData",
]


@dataclass(frozen=True)
class StatusData:
    bot_status: str  # "ACTIVE" | "IDLE" | "NO_DATA"
    last_cycle_at: str | None
    last_event: str | None
    message: str
    gate: str  # market state now: weekend|too_early|closed|manage_only|force_close|ok


@dataclass(frozen=True)
class SummaryData:
    from_date: str | None  # None: all time
    to_date: str
    total_trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate_pct: float
    gross_pnl_usd: float
    profit_factor: float | str  # a number, or "inf" / "n/a"
    largest_winner: dict | None
    largest_loser: dict | None
    avg_winner: float | None
    avg_loser: float | None


@dataclass(frozen=True)
class OpenPositionData:
    symbol: str
    qty: float
    entry_price: float
    stop_price: float  # the stop currently working at the broker
    initial_stop: float
    state: str
    current_price: float | None
    unrealized_r: float | None
    unrealized_pnl_usd: float | None
    opened_at: str
    hold_minutes: float | None
    target_price: float  # entry + 1R, where the stop moves to breakeven
    stop_distance_pct: float | None  # how far the price is above the stop
    target_distance_pct: float | None  # how far the price is below the target (negative: past it)


@dataclass(frozen=True)
class TradeData:
    symbol: str
    qty: float
    entry_price: float
    exit_price: float
    pnl_usd: float
    pnl_pct: float
    r_multiple: float | None
    r_source: str  # "trades_csv" | "decision_log" | "proxy" (an estimate)
    opened_at: str
    closed_at: str
    hold_minutes: float


@dataclass(frozen=True)
class EquityPoint:
    closed_at: str
    symbol: str
    pnl_usd: float
    cumulative_pnl_usd: float


@dataclass(frozen=True)
class SkipData:
    symbol: str
    reasons: list[str]


@dataclass(frozen=True)
class ActionData:
    event: str
    symbol: str | None


@dataclass(frozen=True)
class CycleData:
    at: str
    gate: str
    entries: int
    skipped: int
    skips: list[SkipData]  # capped; `skipped` is the real count
    actions: list[ActionData]
    errors: list[ActionData]


@dataclass(frozen=True)
class PaperProgressData:
    paper_mode: bool
    first_trade_date: str | None  # ET calendar date of the first recorded trade
    days_traded: int  # calendar days from the first trade to today, inclusive
    target_days: int
    days_remaining: int
    reached: bool


@dataclass(frozen=True)
class DashboardData:
    generated_at: str
    period: str  # today | 7d | 30d | all
    status: StatusData
    summary: SummaryData
    paper: PaperProgressData
    cycle: CycleData | None
    r_histogram: list[RBucket]
    open_positions: list[OpenPositionData]
    recent_trades: list[TradeData]
    equity_curve: list[EquityPoint]
    warnings: list[str] = field(default_factory=list)
