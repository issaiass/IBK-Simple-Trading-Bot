"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, Download, Search, X } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useMediaQuery } from "@/hooks/use-media-query";
import { formatDateTime, formatPrice, formatQty, formatR, formatSignedUsd, signOf } from "@/lib/format";
import { signText } from "@/lib/sign";
import { downloadCsv, filterTrades, sortTrades, tradesToCsv, type SortDirection, type SortKey } from "@/lib/trades";
import { cn } from "@/lib/utils";
import type { TradeData } from "@/types/dashboard";

import { EmptyState } from "./empty-state";
import { SectionCard } from "./section-card";
import { SignMarker } from "./sign-marker";

const MAX_ROWS = 20;
const HEAD = "text-xs font-medium text-zinc-400";
const ESTIMATE_HINT =
  "Estimated: no stop was recorded for this trade, so 1% of the entry price is used as the risk.";

interface Column {
  key: SortKey;
  label: string;
  align: "left" | "right";
  /** What the first click sorts by: text A to Z, numbers and dates biggest or newest first. */
  firstDirection: SortDirection;
}

const COLUMNS: Column[] = [
  { key: "symbol", label: "Symbol", align: "left", firstDirection: "asc" },
  { key: "closed_at", label: "Closed", align: "left", firstDirection: "desc" },
  { key: "qty", label: "Qty", align: "right", firstDirection: "desc" },
  { key: "entry_price", label: "Entry", align: "right", firstDirection: "desc" },
  { key: "exit_price", label: "Exit", align: "right", firstDirection: "desc" },
  { key: "pnl_usd", label: "P&L", align: "right", firstDirection: "desc" },
  { key: "r_multiple", label: "R", align: "right", firstDirection: "desc" },
];

/** An R without a recorded stop is a guess; mark it so it isn't mistaken for a measurement. */
const isEstimated = (trade: TradeData): boolean => trade.r_source === "proxy" && trade.r_multiple !== null;

const tradeKey = (t: TradeData): string => `${t.symbol}-${t.closed_at}`;

export function RecentTradesCard({ trades }: { trades: TradeData[] }) {
  const isWide = useMediaQuery("(min-width: 768px)", true);
  const [sort, setSort] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "closed_at",
    direction: "desc",
  });
  const [query, setQuery] = useState("");

  const matching = useMemo(
    () => sortTrades(filterTrades(trades, query), sort.key, sort.direction),
    [trades, query, sort],
  );
  const rows = matching.slice(0, MAX_ROWS);
  const hasEstimates = rows.some(isEstimated);

  const sortBy = (column: Column) =>
    setSort((current) =>
      current.key === column.key
        ? { key: column.key, direction: current.direction === "asc" ? "desc" : "asc" }
        : { key: column.key, direction: column.firstDirection },
    );

  return (
    <SectionCard
      id="trades"
      title="Recent Closed Trades"
      description={`Last ${MAX_ROWS} in the selected period`}
      action={
        trades.length > 0 ? (
          <span data-testid="trade-count" className="text-xs text-zinc-400">
            Showing {rows.length} of {trades.length}
          </span>
        ) : null
      }
    >
      {trades.length === 0 ? (
        <EmptyState title="No closed trades in this period">
          Pick a longer period, or wait for the bot to close a trade.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="relative w-full sm:w-64">
              <Search aria-hidden className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-zinc-500" />
              <Input
                type="search"
                aria-label="Filter by symbol"
                placeholder="Filter by symbol"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="pl-8"
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={matching.length === 0}
              onClick={() => downloadCsv("closed-trades.csv", tradesToCsv(matching))}
            >
              <Download aria-hidden />
              Export CSV
            </Button>
          </div>

          {rows.length === 0 ? (
            <EmptyState title={`No trades match “${query.trim()}”`}>
              <Button type="button" variant="ghost" size="sm" onClick={() => setQuery("")}>
                <X aria-hidden />
                Clear filter
              </Button>
            </EmptyState>
          ) : isWide ? (
            <TradesTable rows={rows} sort={sort} onSort={sortBy} />
          ) : (
            <TradeCards rows={rows} />
          )}

          {hasEstimates ? (
            <p data-testid="estimate-legend" className="text-xs text-zinc-500">
              <span className="font-medium text-zinc-400">est.</span> = estimated R. No stop was recorded for these
              trades, so 1% of the entry price is used as the risk.
            </p>
          ) : null}
        </div>
      )}
    </SectionCard>
  );
}

function RValue({ trade }: { trade: TradeData }): ReactNode {
  return (
    <>
      {formatR(trade.r_multiple)}
      {isEstimated(trade) ? (
        <span className="ml-1.5 rounded bg-white/10 px-1 py-px align-middle text-[10px] font-normal not-italic text-zinc-300">
          est.
        </span>
      ) : null}
    </>
  );
}

interface TableProps {
  rows: TradeData[];
  sort: { key: SortKey; direction: SortDirection };
  onSort: (column: Column) => void;
}

function TradesTable({ rows, sort, onSort }: TableProps) {
  return (
    <Table>
      <TableCaption className="sr-only">Recent closed trades</TableCaption>
      <TableHeader>
        <TableRow className="border-white/10 hover:bg-transparent">
          {COLUMNS.map((column) => {
            const isActive = sort.key === column.key;
            const Icon = !isActive ? ArrowUpDown : sort.direction === "asc" ? ArrowUp : ArrowDown;
            return (
              <TableHead
                key={column.key}
                aria-label={column.label}
                aria-sort={isActive ? (sort.direction === "asc" ? "ascending" : "descending") : undefined}
                className={cn(HEAD, column.align === "right" && "text-right")}
              >
                <button
                  type="button"
                  aria-label={`Sort by ${column.label}`}
                  onClick={() => onSort(column)}
                  className={cn(
                    "inline-flex items-center gap-1 rounded px-1 py-0.5 hover:text-zinc-100 focus-visible:ring-2 focus-visible:ring-emerald-400/60 focus-visible:outline-none",
                    isActive && "text-zinc-100",
                  )}
                >
                  {column.label}
                  <Icon aria-hidden className={cn("size-3", !isActive && "opacity-40")} />
                </button>
              </TableHead>
            );
          })}
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((t) => {
          const estimated = isEstimated(t);
          return (
            <TableRow key={tradeKey(t)} className="border-white/5 hover:bg-white/[0.03]">
              <TableCell>
                <div className="max-w-40 truncate font-medium text-zinc-100" title={t.symbol}>
                  {t.symbol}
                </div>
              </TableCell>
              <TableCell className="text-zinc-400">{formatDateTime(t.closed_at)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatQty(t.qty)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatPrice(t.entry_price)}</TableCell>
              <TableCell className="text-right tabular-nums">{formatPrice(t.exit_price)}</TableCell>
              <TableCell
                data-testid="pnl-cell"
                data-sign={signOf(t.pnl_usd)}
                className={cn("text-right tabular-nums", signText)}
              >
                <SignMarker sign={signOf(t.pnl_usd)} />
                {formatSignedUsd(t.pnl_usd)}
              </TableCell>
              <TableCell
                data-testid="r-cell"
                data-sign={signOf(t.r_multiple)}
                data-estimated={estimated}
                title={estimated ? ESTIMATE_HINT : undefined}
                className={cn("text-right font-medium tabular-nums", signText)}
              >
                <RValue trade={t} />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}

/** One card per trade, for phones: P&L and R are on the card, so nothing hides off-screen. */
function TradeCards({ rows }: { rows: TradeData[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {rows.map((t) => {
        const estimated = isEstimated(t);
        return (
          <li key={tradeKey(t)} className="rounded-lg bg-white/[0.04] p-3">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate font-medium text-zinc-100">{t.symbol}</p>
                <p className="text-xs text-zinc-500">{formatDateTime(t.closed_at)}</p>
              </div>
              <div className="text-right">
                <p>
                  <span data-sign={signOf(t.pnl_usd)} className={cn("font-medium tabular-nums", signText)}>
                    <SignMarker sign={signOf(t.pnl_usd)} />
                    {formatSignedUsd(t.pnl_usd)}
                  </span>
                </p>
                <p
                  data-sign={signOf(t.r_multiple)}
                  data-estimated={estimated}
                  className={cn("text-sm tabular-nums", signText)}
                >
                  <RValue trade={t} />
                </p>
              </div>
            </div>
            <p className="mt-2 text-xs tabular-nums text-zinc-500">
              {formatQty(t.qty)} × {formatPrice(t.entry_price)} → {formatPrice(t.exit_price)}
            </p>
          </li>
        );
      })}
    </ul>
  );
}
