import type { DashboardData, OpenPositionData, TradeData } from "@/types/dashboard";

export const trade = (overrides: Partial<TradeData> = {}): TradeData => ({
  symbol: "NVDA",
  qty: 10,
  entry_price: 235.45,
  exit_price: 235.57,
  pnl_usd: 1.2,
  pnl_pct: 0.05,
  r_multiple: 0.5,
  r_source: "decision_log",
  opened_at: "2026-10-08T12:32:09-04:00",
  closed_at: "2026-10-08T12:32:45-04:00",
  hold_minutes: 0.6,
  ...overrides,
});

export const position = (overrides: Partial<OpenPositionData> = {}): OpenPositionData => ({
  symbol: "BBY",
  qty: 28,
  entry_price: 88.52,
  stop_price: 83.9,
  initial_stop: 83.9,
  state: "pre_breakeven",
  current_price: 90.9,
  unrealized_r: 0.52,
  unrealized_pnl_usd: 66.64,
  opened_at: "2026-10-08T10:15:00-04:00",
  hold_minutes: 165,
  target_price: 93.14,
  stop_distance_pct: 7.7,
  target_distance_pct: 2.5,
  ...overrides,
});

export const emptyDashboard = (): DashboardData => ({
  generated_at: "2026-10-08T13:00:00-04:00",
  period: "today",
  status: {
    bot_status: "NO_DATA", last_cycle_at: null, last_event: null, message: "no cycle data yet", gate: "ok",
  },
  cycle: null,
  paper: {
    paper_mode: true, first_trade_date: null, days_traded: 0, target_days: 14, days_remaining: 14, reached: false,
  },
  summary: {
    from_date: "2026-10-08", to_date: "2026-10-08", total_trades: 0, wins: 0, losses: 0, breakeven: 0, win_rate_pct: 0,
    gross_pnl_usd: 0, profit_factor: "n/a", largest_winner: null, largest_loser: null,
    avg_winner: null, avg_loser: null,
  },
  r_histogram: [
    { label: "≤ -2R", lower: null, upper: -2, count: 0 },
    { label: "-2R to -1R", lower: -2, upper: -1, count: 0 },
    { label: "-1R to 0R", lower: -1, upper: 0, count: 0 },
    { label: "0R to +1R", lower: 0, upper: 1, count: 0 },
    { label: "+1R to +2R", lower: 1, upper: 2, count: 0 },
    { label: "+2R to +3R", lower: 2, upper: 3, count: 0 },
    { label: "> +3R", lower: 3, upper: null, count: 0 },
  ],
  open_positions: [],
  recent_trades: [],
  equity_curve: [],
  warnings: [],
});

export const sampleDashboard = (): DashboardData => {
  const base = emptyDashboard();
  return {
    ...base,
    status: {
      bot_status: "ACTIVE",
      last_cycle_at: "2026-10-08T12:58:00-04:00",
      last_event: "cycle",
      message: "last cycle 2 min ago",
      gate: "ok",
    },
    cycle: {
      at: "2026-10-08T12:58:00-04:00",
      gate: "ok",
      entries: 1,
      skipped: 2,
      skips: [
        { symbol: "AMD", reasons: ["gap too small", "relative volume low"] },
        { symbol: "TSLA", reasons: ["already in position"] },
      ],
      actions: [{ event: "entered", symbol: "BBY" }],
      errors: [],
    },
    summary: {
      from_date: "2026-10-08", to_date: "2026-10-08", total_trades: 5, wins: 1, losses: 4, breakeven: 0, win_rate_pct: 20,
      gross_pnl_usd: -14.88, profit_factor: 0.07,
      largest_winner: { symbol: "NVDA", pnl_usd: 1.2 },
      largest_loser: { symbol: "BBY", pnl_usd: -7 },
      avg_winner: 1.2, avg_loser: -4.02,
    },
    r_histogram: base.r_histogram.map((b, i) => ({ ...b, count: [0, 1, 4, 2, 1, 0, 0][i] })),
    open_positions: [position()],
    recent_trades: [
      trade({ symbol: "BBY", pnl_usd: -7, pnl_pct: -0.28, r_multiple: -0.28, r_source: "proxy" }),
      trade({ symbol: "NVDA", pnl_usd: 1.2, r_multiple: 0.5 }),
    ],
    equity_curve: [
      { closed_at: "2026-10-08T12:32:45-04:00", symbol: "NVDA", pnl_usd: 1.2, cumulative_pnl_usd: 1.2 },
      { closed_at: "2026-10-08T13:07:50-04:00", symbol: "BBY", pnl_usd: -7, cumulative_pnl_usd: -5.8 },
    ],
  };
};
