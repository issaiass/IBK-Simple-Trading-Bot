import type { TradeData } from "@/types/dashboard";

export type SortKey =
  | "symbol"
  | "closed_at"
  | "qty"
  | "entry_price"
  | "exit_price"
  | "pnl_usd"
  | "r_multiple";
export type SortDirection = "asc" | "desc";

/** A copy sorted by `key`. Trades with no value (an undefined R) always go last. */
export function sortTrades(trades: TradeData[], key: SortKey, direction: SortDirection): TradeData[] {
  const sign = direction === "asc" ? 1 : -1;
  return [...trades].sort((a, b) => {
    const left = a[key];
    const right = b[key];
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    if (typeof left === "string" && typeof right === "string") return sign * left.localeCompare(right);
    return sign * (Number(left) - Number(right));
  });
}

/** Trades whose symbol contains `query` (any case); everything for an empty query. */
export function filterTrades(trades: TradeData[], query: string): TradeData[] {
  const needle = query.trim().toLowerCase();
  return needle ? trades.filter((t) => t.symbol.toLowerCase().includes(needle)) : trades;
}

const COLUMNS = [
  "symbol",
  "qty",
  "entry_price",
  "exit_price",
  "pnl_usd",
  "pnl_pct",
  "r_multiple",
  "r_source",
  "opened_at",
  "closed_at",
  "hold_minutes",
] as const satisfies readonly (keyof TradeData)[];

function cell(value: string | number | null): string {
  if (value === null) return "";
  let text = String(value);
  // a text cell starting with = + - @ would run as a formula when the CSV is opened in a spreadsheet
  if (typeof value === "string" && /^[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/** The trades as CSV (RFC 4180 line endings), with raw numbers rather than display formatting. */
export function tradesToCsv(trades: TradeData[]): string {
  const rows = trades.map((t) => COLUMNS.map((column) => cell(t[column])).join(","));
  return [COLUMNS.join(","), ...rows].join("\r\n") + "\r\n";
}

/** Hand the CSV to the browser as a file download. */
export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
