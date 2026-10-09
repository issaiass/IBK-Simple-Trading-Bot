import { RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatAge, formatClock, formatGate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { StatusData } from "@/types/dashboard";

/** Data older than this is flagged: the page refreshes every 30 s, so this means refreshes are failing. */
const STALE_AFTER_MS = 2 * 60_000;

interface StatusHeaderProps {
  status: StatusData;
  /** When this page last refreshed its data (not when the bot last ran). */
  lastUpdated: Date | null;
  /** The current time, ticking, so "Updated 25s ago" keeps moving. */
  now: Date;
  isRefreshing: boolean;
  onRefresh: () => void;
  /** Page-level controls, such as the period selector. */
  controls?: ReactNode;
}

export function StatusHeader({ status, lastUpdated, now, isRefreshing, onRefresh, controls }: StatusHeaderProps) {
  const isStale = lastUpdated !== null && now.getTime() - lastUpdated.getTime() > STALE_AFTER_MS;

  return (
    <header className="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-50">Dashboard</h1>
        <p className="text-sm text-zinc-400">IBKR paper-trading bot</p>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {controls}

        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-full bg-white/[0.04] py-1.5 pl-4 pr-2 text-sm ring-1 ring-white/10">
          <span className="flex items-center gap-2">
            <span className="text-zinc-400">Bot Status:</span>
            <Badge
              data-testid="bot-status"
              data-status={status.bot_status}
              variant="outline"
              className={cn(
                "gap-1.5 border-0 font-semibold",
                "data-[status=ACTIVE]:bg-emerald-400/15 data-[status=ACTIVE]:text-emerald-300",
                "data-[status=IDLE]:bg-amber-400/15 data-[status=IDLE]:text-amber-300",
                "data-[status=NO_DATA]:bg-zinc-400/15 data-[status=NO_DATA]:text-zinc-300",
              )}
            >
              <span
                aria-hidden
                className={cn("size-1.5 rounded-full bg-current", status.bot_status === "ACTIVE" && "animate-pulse")}
              />
              {status.bot_status}
            </Badge>
            <span data-testid="market-state" className="text-zinc-300">
              {formatGate(status.gate)}
            </span>
          </span>

          {status.last_cycle_at ? (
            <span className="flex items-center gap-2">
              <span className="text-zinc-400">Last cycle</span>
              <time dateTime={status.last_cycle_at} className="font-medium tabular-nums text-zinc-100">
                {formatClock(status.last_cycle_at)}
              </time>
            </span>
          ) : (
            <span className="text-zinc-400">{status.message}</span>
          )}

          {lastUpdated ? (
            <span className="flex items-center gap-2 text-xs text-zinc-500">
              <span data-testid="updated">Updated {formatAge(lastUpdated, now)}</span>
              {isStale ? (
                <Badge data-testid="stale" variant="outline" className="border-0 bg-amber-400/15 text-amber-300">
                  Stale
                </Badge>
              ) : null}
            </span>
          ) : null}

          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label="Refresh now"
            data-refreshing={isRefreshing}
            disabled={isRefreshing}
            onClick={onRefresh}
            className="rounded-full text-zinc-300 hover:bg-white/10"
          >
            <RefreshCw aria-hidden className={cn("size-4", isRefreshing && "animate-spin")} />
          </Button>
        </div>
      </div>

      {/* Screen readers hear each refresh without it stealing focus. */}
      <p role="status" className="sr-only">
        {lastUpdated ? `Dashboard updated ${formatClock(lastUpdated)}` : ""}
      </p>
    </header>
  );
}
