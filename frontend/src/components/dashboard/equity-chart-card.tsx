"use client";

import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";

import { buildChartPath, nearestIndex, niceTicks } from "@/lib/chart";
import { formatDateTime, formatSignedUsd, formatUsd, signOf } from "@/lib/format";
import { signText } from "@/lib/sign";
import { cn } from "@/lib/utils";
import type { EquityPoint, Period } from "@/types/dashboard";

import { EmptyState } from "./empty-state";
import { SectionCard } from "./section-card";
import { SignMarker } from "./sign-marker";

const BOX = { width: 600, height: 220, padding: 12 };
/** Space on the left for the dollar labels. */
const GUTTER = "3.25rem";

/** "$0", "-$10", "$1,500": whole dollars are enough for an axis. */
function formatTick(value: number): string {
  const text = formatUsd(Math.abs(value)).replace(/\.00$/, "");
  return value < 0 ? `-${text}` : text;
}

interface EquityChartCardProps {
  points: EquityPoint[];
  period: Period;
}

export function EquityChartCard({ points, period }: EquityChartCardProps) {
  void period; // every period is drawn the same way; kept so the card can word itself per period later
  const gradientId = useId();
  const [selected, setSelected] = useState<number | null>(null);

  // The curve starts from zero, so even a single trade has a line to show.
  const values = [0, ...points.map((p) => p.cumulative_pnl_usd)];
  const chart = points.length === 0 ? null : buildChartPath(values, BOX);
  const latest = points.at(-1)?.cumulative_pnl_usd ?? null;
  const colour = (latest ?? 0) >= 0 ? "#34d399" : "#fb7185"; // emerald-400 / rose-400
  const last = values.length - 1;
  const active = selected ?? last;

  const move = (delta: number) => setSelected((current) => Math.min(last, Math.max(0, (current ?? last) + delta)));

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "ArrowLeft") move(-1);
    else if (event.key === "ArrowRight") move(1);
    else return;
    event.preventDefault();
  };

  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width <= 0) return;
    setSelected(nearestIndex((event.clientX - rect.left - remToPx(GUTTER)) / (rect.width - remToPx(GUTTER)), values.length));
  };

  return (
    <SectionCard
      title="Cumulative P&L"
      description="Closed trades in this period, in the order they closed"
      action={
        latest === null ? null : (
          <span
            data-testid="equity-latest"
            data-sign={signOf(latest)}
            className={cn("text-lg font-semibold tabular-nums", signText)}
          >
            <SignMarker sign={signOf(latest)} />
            {formatSignedUsd(latest)}
          </span>
        )
      }
    >
      {chart === null ? (
        <EmptyState title="No closed trades in this period">
          Pick a longer period, or wait for the bot to close a trade.
        </EmptyState>
      ) : (
        <div className="flex flex-col gap-3">
          <Readout points={points} index={active} />

          <div
            role="group"
            aria-label="Chart readout: use the left and right arrow keys to step through trades"
            tabIndex={0}
            onKeyDown={onKeyDown}
            onPointerMove={onPointerMove}
            onPointerLeave={() => setSelected(null)}
            onBlur={() => setSelected(null)}
            className="relative h-56 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/50"
          >
            <svg
              role="img"
              aria-label="Cumulative P&L chart"
              viewBox={`0 0 ${BOX.width} ${BOX.height}`}
              preserveAspectRatio="none"
              className="absolute inset-y-0 right-0 h-full"
              style={{ left: GUTTER, width: `calc(100% - ${GUTTER})` }}
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={colour} stopOpacity="0.35" />
                  <stop offset="100%" stopColor={colour} stopOpacity="0" />
                </linearGradient>
              </defs>
              {niceTicks(Math.min(...values), Math.max(...values)).map((tick) => (
                <line
                  key={tick}
                  x1={BOX.padding}
                  x2={BOX.width - BOX.padding}
                  y1={chart.yOf(tick)}
                  y2={chart.yOf(tick)}
                  stroke="white"
                  strokeOpacity={tick === 0 ? 0.25 : 0.07}
                  strokeDasharray={tick === 0 ? "4 4" : undefined}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              <path d={chart.area} fill={`url(#${gradientId})`} />
              <path
                data-testid="equity-line"
                d={chart.line}
                fill="none"
                stroke={colour}
                strokeWidth="2"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            </svg>

            {/* Axis labels and the marker are HTML on top of the SVG, so the text is never stretched. */}
            <div aria-hidden className="pointer-events-none absolute inset-0">
              {niceTicks(Math.min(...values), Math.max(...values)).map((tick) => (
                <span
                  key={tick}
                  data-testid="y-tick"
                  className="absolute left-0 -translate-y-1/2 text-[11px] tabular-nums text-zinc-500"
                  style={{ top: `${(chart.yOf(tick) / BOX.height) * 100}%`, width: GUTTER }}
                >
                  {formatTick(tick)}
                </span>
              ))}
              <span
                className="absolute size-3 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white/70"
                style={{
                  backgroundColor: colour,
                  left: `calc(${GUTTER} + (100% - ${GUTTER}) * ${chart.points[active].x / BOX.width})`,
                  top: `${(chart.points[active].y / BOX.height) * 100}%`,
                }}
              />
            </div>
          </div>

          <div
            className="flex justify-between text-[11px] tabular-nums text-zinc-500"
            style={{ paddingLeft: GUTTER }}
          >
            <span data-testid="x-start">{formatDateTime(points[0].closed_at)}</span>
            <span data-testid="x-end">{formatDateTime(points[points.length - 1].closed_at)}</span>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

/** The selected point in words: the same information a sighted viewer gets by hovering. */
function Readout({ points, index }: { points: EquityPoint[]; index: number }) {
  if (index === 0) {
    return (
      <p data-testid="readout" className="text-xs text-zinc-400">
        Start of period · $0.00
      </p>
    );
  }
  const point = points[index - 1];
  return (
    <p data-testid="readout" className="flex flex-wrap items-center gap-x-2 text-xs text-zinc-400">
      <span className="font-medium text-zinc-100">{point.symbol}</span>
      <span>{formatDateTime(point.closed_at)}</span>
      <span data-sign={signOf(point.pnl_usd)} className={cn("tabular-nums", signText)}>
        {formatSignedUsd(point.pnl_usd)}
      </span>
      <span>·</span>
      <span>
        Total{" "}
        <span data-sign={signOf(point.cumulative_pnl_usd)} className={cn("tabular-nums", signText)}>
          {formatSignedUsd(point.cumulative_pnl_usd)}
        </span>
      </span>
    </p>
  );
}

/** rem to pixels at the page's font size (16 px unless the viewer changed it). */
function remToPx(rem: string): number {
  const size = typeof document === "undefined" ? 16 : parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  return parseFloat(rem) * size;
}
