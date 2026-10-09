/** The dashboard API contract. Mirrors src/trading_bot/api/schemas.py in the Python backend. */

export type BotStatus = "ACTIVE" | "IDLE" | "NO_DATA";

/** Where a trade's initial stop (and so its R) came from; "proxy" is an estimate. */
export type RSource = "trades_csv" | "decision_log" | "proxy";

/** How much history every section covers. */
export type Period = "today" | "7d" | "30d" | "all";

/** The market state the bot's time gate is in right now. */
export type MarketGate = "weekend" | "too_early" | "closed" | "manage_only" | "force_close" | "ok";

export interface StatusData {
  bot_status: BotStatus;
  last_cycle_at: string | null;
  last_event: string | null;
  message: string;
  gate: MarketGate;
}

export interface TradeHighlight {
  symbol: string;
  pnl_usd: number;
}

export interface SummaryData {
  /** First day covered (ET), or null for all time. */
  from_date: string | null;
  to_date: string;
  total_trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate_pct: number;
  gross_pnl_usd: number;
  /** A number, or "inf" (no losses) / "n/a" (no trades). */
  profit_factor: number | "inf" | "n/a";
  largest_winner: TradeHighlight | null;
  largest_loser: TradeHighlight | null;
  avg_winner: number | null;
  avg_loser: number | null;
}

export interface RBucket {
  label: string;
  /** null = open-ended */
  lower: number | null;
  upper: number | null;
  count: number;
}

export interface OpenPositionData {
  symbol: string;
  qty: number;
  entry_price: number;
  /** The stop currently working at the broker. */
  stop_price: number;
  initial_stop: number;
  state: string;
  current_price: number | null;
  unrealized_r: number | null;
  unrealized_pnl_usd: number | null;
  opened_at: string;
  hold_minutes: number | null;
  /** Entry + 1R: where the stop moves to breakeven. */
  target_price: number;
  /** % the price is above the stop. */
  stop_distance_pct: number | null;
  /** % the price must still rise to reach the target (negative: already past it). */
  target_distance_pct: number | null;
}

export interface TradeData {
  symbol: string;
  qty: number;
  entry_price: number;
  exit_price: number;
  pnl_usd: number;
  pnl_pct: number;
  r_multiple: number | null;
  r_source: RSource;
  opened_at: string;
  closed_at: string;
  hold_minutes: number;
}

export interface EquityPoint {
  closed_at: string;
  symbol: string;
  pnl_usd: number;
  cumulative_pnl_usd: number;
}

export interface CycleAction {
  event: string;
  symbol: string | null;
}

export interface CycleSkip {
  symbol: string;
  reasons: string[];
}

/** What the bot's most recent run did. */
export interface CycleData {
  at: string;
  gate: string;
  entries: number;
  /** Real count; `skips` is capped. */
  skipped: number;
  skips: CycleSkip[];
  actions: CycleAction[];
  errors: CycleAction[];
}

/** How far the paper run is toward the recommended two weeks (always over the whole history). */
export interface PaperProgressData {
  /** False when the bot is configured for a live account. */
  paper_mode: boolean;
  first_trade_date: string | null;
  /** Calendar days from the first trade to today, inclusive. */
  days_traded: number;
  target_days: number;
  days_remaining: number;
  reached: boolean;
}

export interface DashboardData {
  generated_at: string;
  period: Period;
  status: StatusData;
  summary: SummaryData;
  paper: PaperProgressData;
  cycle: CycleData | null;
  r_histogram: RBucket[];
  open_positions: OpenPositionData[];
  recent_trades: TradeData[];
  equity_curve: EquityPoint[];
  warnings: string[];
}
