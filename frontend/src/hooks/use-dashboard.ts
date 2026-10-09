"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { fetchDashboard } from "@/lib/api";
import type { DashboardData, Period } from "@/types/dashboard";

export const REFRESH_INTERVAL_MS = 30_000;

export interface DashboardState {
  data: DashboardData | null;
  /** The last refresh's error. Set alongside stale `data` when a later refresh fails. */
  error: string | null;
  /** True until the first answer (or error) arrives. */
  isLoading: boolean;
  /** True while a later fetch (timer, manual or a new period) is in flight. */
  isRefreshing: boolean;
  lastUpdated: Date | null;
}

export interface DashboardControls extends DashboardState {
  period: Period;
  setPeriod: (period: Period) => void;
  /** Fetch now instead of waiting for the next tick. */
  refresh: () => void;
}

interface Options {
  fetcher?: (period: Period) => Promise<DashboardData>;
  intervalMs?: number;
  initialPeriod?: Period;
}

const INITIAL: DashboardState = {
  data: null,
  error: null,
  isLoading: true,
  isRefreshing: false,
  lastUpdated: null,
};

/** Loads the dashboard for a period and refreshes it on an interval, keeping the last good data on failure. */
export function useDashboard({
  fetcher = fetchDashboard,
  intervalMs = REFRESH_INTERVAL_MS,
  initialPeriod = "today",
}: Options = {}): DashboardControls {
  const [state, setState] = useState<DashboardState>(INITIAL);
  const [period, setPeriod] = useState<Period>(initialPeriod);

  // Always call the latest fetcher without restarting the polling when its identity changes.
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  // Set by the effect below so `refresh` can reuse its loader.
  const loadRef = useRef<() => void>(() => {});
  const refresh = useCallback(() => loadRef.current(), []);

  useEffect(() => {
    let active = true; // false once this period/mount is replaced: late answers are dropped

    const load = async () => {
      setState((previous) => (previous.isLoading ? previous : { ...previous, isRefreshing: true }));
      try {
        const data = await fetcherRef.current(period);
        if (active) {
          setState({ data, error: null, isLoading: false, isRefreshing: false, lastUpdated: new Date() });
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        if (active) {
          setState((previous) => ({ ...previous, error: message, isLoading: false, isRefreshing: false }));
        }
      }
    };

    loadRef.current = () => void load();
    void load();
    const timer = setInterval(() => void load(), intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [intervalMs, period]);

  return { ...state, period, setPeriod, refresh };
}
