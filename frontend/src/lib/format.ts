import type { CycleAction, MarketGate, Period, SummaryData } from "@/types/dashboard";

/** Display formatting. Times are always US Eastern: the bot trades on New York hours. */

export type Sign = "positive" | "negative" | "zero" | "unknown";

const TIME_ZONE = "America/New_York";
const DASH = "—";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const formatUsd = (value: number): string => usd.format(value);

/** "+$20.00" / "-$7.00" / "$0.00": an explicit sign, except on zero. */
export const formatSignedUsd = (value: number): string =>
  value > 0 ? `+${usd.format(value)}` : usd.format(value);

export const formatPrice = formatUsd;

export const formatPct = (value: number, digits = 1): string => `${value.toFixed(digits)}%`;

export const formatQty = (value: number): string => String(value);

export function formatProfitFactor(value: number | "inf" | "n/a"): string {
  if (value === "inf") return "∞";
  if (value === "n/a") return DASH;
  return value.toFixed(2);
}

export function signOf(value: number | null): Sign {
  if (value === null) return "unknown";
  if (value > 0) return "positive";
  if (value < 0) return "negative";
  return "zero";
}

/** "+0.50R" / "-0.28R" / "0.00R", or a dash when R is not defined. */
export function formatR(value: number | null): string {
  if (value === null) return DASH;
  const rounded = Number(value.toFixed(2));
  if (rounded === 0) return "0.00R";
  return `${rounded > 0 ? "+" : ""}${rounded.toFixed(2)}R`;
}

const clock = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dateParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TIME_ZONE,
  month: "short",
  day: "numeric",
});

export const formatClock = (value: string | Date): string => `${clock.format(new Date(value))} ET`;

/** "Oct 8, 12:58" */
export function formatDateTime(value: string | Date): string {
  const date = new Date(value);
  return `${dateParts.format(date)}, ${clock.format(date)}`;
}

export function formatHold(minutes: number): string {
  if (minutes < 1) return "<1m";
  const total = Math.round(minutes);
  if (total < 60) return `${total}m`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`;
}

const shortDate = new Intl.DateTimeFormat("en-US", { timeZone: "UTC", month: "short", day: "numeric" });

/** "Oct 8" from a calendar date such as "2026-10-08" (no time zone shifts it). */
const formatCalendarDate = (isoDate: string): string => shortDate.format(new Date(`${isoDate}T00:00:00Z`));

/** What the selected period covers, for the card headings. */
export function formatPeriodLabel(period: Period, summary: SummaryData): string {
  const end = formatCalendarDate(summary.to_date);
  if (period === "all" || summary.from_date === null) return "All time";
  if (period === "today") return `Today · ${end}`;
  const days = period === "7d" ? 7 : 30;
  return `Last ${days} days · ${formatCalendarDate(summary.from_date)} – ${end}`;
}

const GATE_TEXT: Record<MarketGate, string> = {
  weekend: "Market closed (weekend)",
  too_early: "Before the 10:00 ET open",
  closed: "Market closed",
  manage_only: "Managing positions only",
  force_close: "Closing positions for the day",
  ok: "Scanning for entries",
};

/** The bot's current market state in plain words. */
export const formatGate = (gate: MarketGate): string => GATE_TEXT[gate] ?? gate;

const STATE_TEXT: Record<string, string> = {
  pre_breakeven: "Waiting for breakeven",
  post_breakeven_no_partial: "Breakeven, partial pending",
  post_breakeven_partial_done: "Partial taken, trailing",
};

export const formatPositionState = (state: string): string => STATE_TEXT[state] ?? state;

export const formatDistance = (pct: number | null): string => (pct === null ? DASH : formatPct(pct, 2));

/** "just now", "45s ago", "3m ago", "2h ago". */
export function formatAge(from: Date, now: Date): string {
  const seconds = Math.max(0, Math.round((now.getTime() - from.getTime()) / 1000));
  if (seconds < 10) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return `${Math.floor(seconds / 3600)}h ago`;
}

const ACTION_TEXT: Record<string, (symbol: string) => string> = {
  entered: (s) => `Entered ${s}`,
  partial_sold: (s) => `Sold a partial of ${s}`,
  breakeven_stop: (s) => `Moved ${s} to breakeven`,
  stop_moved: (s) => `Trailed the stop on ${s}`,
  stopped_out: (s) => `${s} was stopped out`,
  force_close: (s) => `Closed ${s} for the day`,
  stop_restored: (s) => `Restored the stop on ${s}`,
};

/** One cycle event as a sentence: "Entered BBY", "Stop move failed: X", "Max trades reached". */
export function describeAction({ event, symbol }: CycleAction): string {
  const known = ACTION_TEXT[event];
  if (known && symbol !== null) return known(symbol);
  const words = event.replaceAll("_", " ");
  const sentence = words.charAt(0).toUpperCase() + words.slice(1);
  return symbol === null ? sentence : `${sentence}: ${symbol}`;
}
