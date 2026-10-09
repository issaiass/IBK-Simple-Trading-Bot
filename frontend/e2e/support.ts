import type { Page } from "@playwright/test";

import { sampleDashboard, trade } from "../src/test/fixtures";
import type { DashboardData, Period } from "../src/types/dashboard";

export const DASHBOARD_API = "**/api/dashboard**";

/**
 * Serve a dashboard instead of the real backend. Returns the periods that were requested, in order,
 * so a test can check what the page asked for.
 */
export async function mockDashboard(
  page: Page,
  build: (period: Period) => DashboardData = (period) => ({ ...sampleDashboard(), period }),
): Promise<Period[]> {
  const requested: Period[] = [];
  await page.route(DASHBOARD_API, (route) => {
    const period = (new URL(route.request().url()).searchParams.get("period") ?? "today") as Period;
    requested.push(period);
    return route.fulfill({ json: build(period) });
  });
  return requested;
}

/** Make every dashboard request fail like an unreachable backend. */
export async function breakDashboard(page: Page): Promise<void> {
  await page.route(DASHBOARD_API, (route) => route.abort("connectionrefused"));
}

/** Collect uncaught page errors and console errors for later assertion. */
export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

/** A dashboard with 25 trades, one very long symbol and a losing open position, for stress tests. */
export function crowdedDashboard(period: Period = "today"): DashboardData {
  const base = sampleDashboard();
  const trades = Array.from({ length: 25 }, (_, i) =>
    trade({
      symbol: i === 3 ? "BRK.B-WARRANT-2027" : `S${String(i).padStart(2, "0")}`,
      pnl_usd: i % 3 === 0 ? -(i + 1) : i + 1,
      r_multiple: i % 3 === 0 ? -0.5 : 1.2,
      r_source: i % 2 === 0 ? "proxy" : "decision_log",
      closed_at: `2026-10-08T${String(15 - Math.floor(i / 12)).padStart(2, "0")}:${String(59 - ((i * 5) % 60)).padStart(2, "0")}:00-04:00`,
    }),
  );
  return {
    ...base,
    period,
    recent_trades: trades,
    open_positions: [
      {
        ...base.open_positions[0],
        symbol: "LOSER",
        current_price: 80,
        unrealized_r: -1.5,
        unrealized_pnl_usd: -238.56,
        stop_distance_pct: 4.9,
        target_distance_pct: 16.4,
      },
    ],
  };
}
