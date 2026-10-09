"use client";

import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMediaQuery } from "@/hooks/use-media-query";
import {
  formatDistance,
  formatHold,
  formatPositionState,
  formatPrice,
  formatQty,
  formatR,
  formatSignedUsd,
  signOf,
} from "@/lib/format";
import { signText } from "@/lib/sign";
import { cn } from "@/lib/utils";
import type { OpenPositionData } from "@/types/dashboard";

import { EmptyState } from "./empty-state";
import { SectionCard } from "./section-card";
import { SignMarker } from "./sign-marker";

const HEAD = "text-xs font-medium text-zinc-400";
const RIGHT = "text-right";

/** How far the price is from the stop, in words. */
const stopDistance = (p: OpenPositionData): string =>
  p.stop_distance_pct === null ? "—" : `${formatDistance(p.stop_distance_pct)} away`;

/** How far the price is from the +1R target, in words. */
function targetDistance(p: OpenPositionData): string {
  if (p.target_distance_pct === null) return "—";
  return p.target_distance_pct <= 0 ? "reached" : `${formatDistance(p.target_distance_pct)} to go`;
}

const held = (p: OpenPositionData): string => (p.hold_minutes === null ? "—" : formatHold(p.hold_minutes));

function PnlValue({ value }: { value: number | null }) {
  if (value === null) return <>—</>;
  return (
    <>
      <SignMarker sign={signOf(value)} />
      {formatSignedUsd(value)}
    </>
  );
}

export function OpenPositionsCard({ positions }: { positions: OpenPositionData[] }) {
  const isWide = useMediaQuery("(min-width: 768px)", true);

  return (
    <SectionCard
      id="positions"
      title="Open Positions"
      action={
        <Badge data-testid="position-count" variant="outline" className="border-white/10 text-zinc-300">
          {positions.length}
        </Badge>
      }
    >
      {positions.length === 0 ? (
        <EmptyState title="No open positions">
          Positions appear here while the bot is in a trade, with live price, stop and target.
        </EmptyState>
      ) : isWide ? (
        <PositionsTable positions={positions} />
      ) : (
        <PositionCards positions={positions} />
      )}
    </SectionCard>
  );
}

function PositionsTable({ positions }: { positions: OpenPositionData[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="border-white/10 hover:bg-transparent">
          <TableHead className={HEAD}>Symbol</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Qty</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Entry</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Price</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Stop</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Target (+1R)</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Held</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>Unrealized R</TableHead>
          <TableHead className={cn(HEAD, RIGHT)}>P&amp;L</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {positions.map((p) => (
          <TableRow key={p.symbol} className="border-white/5 hover:bg-white/[0.03]">
            <TableCell>
              <div className="max-w-40 truncate font-medium text-zinc-100" title={p.symbol}>
                {p.symbol}
              </div>
              <div className="text-xs text-zinc-500">{formatPositionState(p.state)}</div>
            </TableCell>
            <TableCell className={cn(RIGHT, "tabular-nums")}>{formatQty(p.qty)}</TableCell>
            <TableCell className={cn(RIGHT, "tabular-nums")}>{formatPrice(p.entry_price)}</TableCell>
            <TableCell className={cn(RIGHT, "tabular-nums")}>
              {p.current_price === null ? "—" : formatPrice(p.current_price)}
            </TableCell>
            <TableCell className={cn(RIGHT, "tabular-nums")}>
              <div>{formatPrice(p.stop_price)}</div>
              <div data-testid="stop-distance" className="text-xs text-zinc-500">{stopDistance(p)}</div>
            </TableCell>
            <TableCell className={cn(RIGHT, "tabular-nums")}>
              <div>{formatPrice(p.target_price)}</div>
              <div data-testid="target-distance" className="text-xs text-zinc-500">{targetDistance(p)}</div>
            </TableCell>
            <TableCell data-testid="held" className={cn(RIGHT, "tabular-nums text-zinc-400")}>{held(p)}</TableCell>
            <TableCell
              data-testid="unrealized-r"
              data-sign={signOf(p.unrealized_r)}
              className={cn(RIGHT, "font-medium tabular-nums", signText)}
            >
              {formatR(p.unrealized_r)}
            </TableCell>
            <TableCell data-sign={signOf(p.unrealized_pnl_usd)} className={cn(RIGHT, "tabular-nums", signText)}>
              <PnlValue value={p.unrealized_pnl_usd} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

/** One card per position, for phones: everything important without sideways scrolling. */
function PositionCards({ positions }: { positions: OpenPositionData[] }) {
  return (
    <ul className="flex flex-col gap-3">
      {positions.map((p) => (
        <li key={p.symbol} className="rounded-lg bg-white/[0.04] p-3">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate font-medium text-zinc-100">{p.symbol}</p>
              <p className="text-xs text-zinc-500">{formatPositionState(p.state)}</p>
            </div>
            <div className="text-right">
              <p
                data-sign={signOf(p.unrealized_r)}
                className={cn("font-medium tabular-nums", signText)}
              >
                {formatR(p.unrealized_r)}
              </p>
              <p data-sign={signOf(p.unrealized_pnl_usd)} className={cn("text-sm tabular-nums", signText)}>
                <PnlValue value={p.unrealized_pnl_usd} />
              </p>
            </div>
          </div>
          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <Row label="Qty" value={formatQty(p.qty)} />
            <Row label="Held" value={held(p)} />
            <Row label="Entry" value={formatPrice(p.entry_price)} />
            <Row label="Price" value={p.current_price === null ? "—" : formatPrice(p.current_price)} />
            <Row label="Stop" value={`${formatPrice(p.stop_price)} · ${stopDistance(p)}`} />
            <Row label="Target" value={`${formatPrice(p.target_price)} · ${targetDistance(p)}`} />
          </dl>
        </li>
      ))}
    </ul>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-zinc-500">{label}</dt>
      <dd className="tabular-nums text-zinc-300">{value}</dd>
    </div>
  );
}
