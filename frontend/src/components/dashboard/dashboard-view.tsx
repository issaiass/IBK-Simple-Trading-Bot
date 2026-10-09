"use client";

import { TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";

import { useDashboard } from "@/hooks/use-dashboard";
import { useNow } from "@/hooks/use-now";
import { formatClock } from "@/lib/format";
import { browserStorage, readStoredPeriod, storePeriod } from "@/lib/period";
import type { DashboardData, Period } from "@/types/dashboard";

import { CycleCard } from "./cycle-card";
import { DashboardSkeleton } from "./dashboard-skeleton";
import { EquityChartCard } from "./equity-chart-card";
import { OpenPositionsCard } from "./open-positions-card";
import { PaperProgress } from "./paper-progress";
import { PeriodSelect } from "./period-select";
import { PnlSummaryCard } from "./pnl-summary-card";
import { RHistogramCard } from "./r-histogram-card";
import { RecentTradesCard } from "./recent-trades-card";
import { StatusHeader } from "./status-header";

interface DashboardViewProps {
  fetcher?: (period: Period) => Promise<DashboardData>;
  intervalMs?: number;
}

/** Two grid columns wide, with its card stretched to the height of the row. */
const WIDE_CELL = "xl:col-span-2 [&>section]:h-full";

function Banner({ role, children }: { role?: "alert"; children: ReactNode }) {
  return (
    <div
      role={role}
      className="flex items-start gap-3 rounded-xl bg-amber-400/10 px-4 py-3 text-sm text-amber-200 ring-1 ring-amber-400/25"
    >
      <TriangleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
      <div className="flex flex-col gap-1">{children}</div>
    </div>
  );
}

export function DashboardView({ fetcher, intervalMs }: DashboardViewProps) {
  // The viewer's last choice. Safe to read here: the first render is the skeleton on server and client alike.
  const [initialPeriod] = useState(() => readStoredPeriod(browserStorage()));
  const { data, error, isLoading, isRefreshing, lastUpdated, period, setPeriod, refresh } = useDashboard({
    fetcher,
    intervalMs,
    initialPeriod,
  });
  const now = useNow();

  const choosePeriod = (next: Period) => {
    storePeriod(next, browserStorage());
    setPeriod(next);
  };

  if (!data) {
    if (isLoading) return <DashboardSkeleton />;
    return (
      <Banner role="alert">
        <p className="font-medium">Couldn&apos;t load the dashboard</p>
        <p>{error}</p>
        <p className="text-amber-200/70">
          Is the API running? Start it with <code className="font-mono">uv run serve-api</code>.
        </p>
      </Banner>
    );
  }

  return (
    <div aria-busy={isRefreshing} className="flex flex-col gap-6">
      <StatusHeader
        status={data.status}
        lastUpdated={lastUpdated}
        now={now}
        isRefreshing={isRefreshing}
        onRefresh={refresh}
        controls={<PeriodSelect value={period} onChange={choosePeriod} />}
      />

      {error ? (
        <Banner role="alert">
          <p>
            Refresh failed ({error}). Showing the last data
            {lastUpdated ? ` from ${formatClock(lastUpdated)}` : ""}.
          </p>
        </Banner>
      ) : null}

      {data.warnings.length > 0 ? (
        <Banner>
          <ul className="flex flex-col gap-1">
            {data.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </Banner>
      ) : null}

      <PaperProgress progress={data.paper} />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <PnlSummaryCard summary={data.summary} period={data.period} />
        <div className={WIDE_CELL}>
          <EquityChartCard points={data.equity_curve} period={data.period} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3">
        <RHistogramCard buckets={data.r_histogram} />
        <div className={WIDE_CELL}>
          <OpenPositionsCard positions={data.open_positions} />
        </div>
      </div>

      <CycleCard cycle={data.cycle} />

      <RecentTradesCard trades={data.recent_trades} />
    </div>
  );
}
