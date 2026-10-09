import { expect, test } from "@playwright/test";

import { sampleDashboard } from "../src/test/fixtures";
import { breakDashboard, collectErrors, crowdedDashboard, DASHBOARD_API, mockDashboard } from "./support";

test.describe("dashboard with data", () => {
  test("shows every section with the API's numbers and no console errors", async ({ page }) => {
    const errors = collectErrors(page);
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.getByText("ACTIVE")).toBeVisible();
    for (const title of [
      "Today's P&L",
      "Cumulative P&L",
      "R-Multiple Distribution",
      "Open Positions",
      "Last Cycle",
      "Recent Closed Trades",
    ]) {
      await expect(page.getByText(title, { exact: true })).toBeVisible();
    }
    await expect(page.getByText("-$14.88").first()).toBeVisible();
    await expect(page.getByText("20.0%")).toBeVisible();
    await expect(page.getByRole("cell", { name: "BBY" }).first()).toBeVisible();
    expect(errors).toEqual([]);
  });

  test("colours losses and gains through data-sign, with a marker that does not rely on colour", async ({ page }) => {
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.locator('[data-sign="negative"]').first()).toBeVisible();
    await expect(page.locator('[data-sign="positive"]').first()).toBeVisible();
    await expect(page.getByTestId("total-pnl").locator("[data-marker]")).toHaveText("▼");
  });

  test("marks a proxy R as an estimate and explains it", async ({ page }) => {
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.locator("[data-estimated=true]").first()).toContainText("est.");
    await expect(page.getByTestId("estimate-legend")).toContainText("1% of the entry price");
  });

  test("explains the market state and what the last cycle did", async ({ page }) => {
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.getByTestId("market-state")).toHaveText("Scanning for entries");
    await expect(page.getByText("Entered BBY")).toBeVisible();
    await page.getByText(/why were 2 candidates skipped/i).click();
    await expect(page.getByText(/gap too small, relative volume low/)).toBeVisible();
  });

  test("shows open-position context: state, distances and holding time", async ({ page }) => {
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.getByText("Waiting for breakeven")).toBeVisible();
    await expect(page.getByTestId("stop-distance")).toContainText("away");
    await expect(page.getByTestId("target-distance")).toContainText("to go");
    await expect(page.getByTestId("held")).toHaveText("2h 45m");
  });
});

test.describe("paper run progress", () => {
  test("shows how far the two-week paper run is, whatever period is selected", async ({ page }) => {
    await mockDashboard(page, (period) => ({
      ...sampleDashboard(),
      period,
      paper: { paper_mode: true, first_trade_date: "2026-10-03", days_traded: 6, target_days: 14, days_remaining: 8, reached: false },
    }));
    await page.goto("/");

    const region = page.getByRole("region", { name: "Paper trading" });
    await expect(region).toContainText("Day 6 of 14");
    await expect(region).toContainText("8 days to go");
    await expect(page.getByRole("progressbar", { name: "Paper trading run" })).toHaveAttribute("aria-valuenow", "6");
  });

  test("warns when the bot is configured for a live account", async ({ page }) => {
    await mockDashboard(page, (period) => ({
      ...sampleDashboard(),
      period,
      paper: { paper_mode: false, first_trade_date: null, days_traded: 0, target_days: 14, days_remaining: 14, reached: false },
    }));
    await page.goto("/");

    await expect(page.getByText("configured for a live account")).toBeVisible();
    await expect(page.getByRole("progressbar")).toHaveCount(0);
  });
});

test.describe("period selection", () => {
  test("asks the API for the chosen period, and remembers it after a reload", async ({ page }) => {
    const requested = await mockDashboard(page);
    await page.goto("/");
    await expect(page.getByRole("radio", { name: "Today" })).toBeChecked();

    await page.getByText("7 days", { exact: true }).click();
    await expect(page.getByRole("radio", { name: "7 days" })).toBeChecked();
    await expect.poll(() => requested.at(-1)).toBe("7d");

    await page.reload();
    await expect(page.getByRole("radio", { name: "7 days" })).toBeChecked();
    await expect.poll(() => requested.at(-1)).toBe("7d");
  });

  test("an empty period is explained, not blank", async ({ page }) => {
    await mockDashboard(page, (period) => {
      const data = { ...sampleDashboard(), period };
      return { ...data, recent_trades: [], equity_curve: [], open_positions: [] };
    });
    await page.goto("/");

    await expect(page.getByText("No closed trades in this period").first()).toBeVisible();
    await expect(page.getByText("No open positions")).toBeVisible();
  });
});

test.describe("trades table", () => {
  test.beforeEach(async ({ page }) => {
    await mockDashboard(page, (period) => crowdedDashboard(period));
    await page.goto("/");
  });

  test("shows 20 of the 25 trades and says so", async ({ page }) => {
    await expect(page.getByTestId("trade-count")).toHaveText("Showing 20 of 25");
    await expect(page.getByTestId("r-cell")).toHaveCount(20);
  });

  test("sorts by P&L from the header", async ({ page }) => {
    await page.getByRole("button", { name: "Sort by P&L" }).click();
    const first = page.getByTestId("pnl-cell").first();
    await expect(first).toContainText("+$24.00");
    await page.getByRole("button", { name: "Sort by P&L" }).click();
    await expect(page.getByTestId("pnl-cell").first()).toContainText("-$25.00");
  });

  test("filters by symbol, including a very long one", async ({ page }) => {
    await page.getByRole("searchbox", { name: "Filter by symbol" }).fill("brk");
    await expect(page.getByText("BRK.B-WARRANT-2027")).toBeVisible();
    await expect(page.getByTestId("trade-count")).toHaveText("Showing 1 of 25");
    await page.getByRole("searchbox", { name: "Filter by symbol" }).fill("zzz");
    await expect(page.getByText(/no trades match/i)).toBeVisible();
    await page.getByRole("button", { name: "Clear filter" }).click();
    await expect(page.getByTestId("trade-count")).toHaveText("Showing 20 of 25");
  });

  test("exports the trades as a CSV file", async ({ page }) => {
    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Export CSV" }).click();
    const file = await download;
    expect(file.suggestedFilename()).toBe("closed-trades.csv");
    const path = await file.path();
    const { readFileSync } = await import("node:fs");
    const csv = readFileSync(path, "utf8");
    expect(csv.split("\r\n")[0]).toContain("symbol,qty,entry_price");
    expect(csv.trim().split("\r\n")).toHaveLength(26); // header + all 25, not only the 20 on screen
  });

  test("shows a losing open position in the loss colour", async ({ page }) => {
    const row = page.getByRole("row", { name: /LOSER/ });
    await expect(row.locator('[data-sign="negative"]').first()).toBeVisible();
    await expect(row).toContainText("-1.50R");
  });
});

test.describe("refresh and staleness", () => {
  test("refresh now fetches again", async ({ page }) => {
    const requested = await mockDashboard(page);
    await page.goto("/");
    await expect(page.getByText("-$14.88").first()).toBeVisible();
    const before = requested.length;
    await page.getByRole("button", { name: "Refresh now" }).click();
    await expect.poll(() => requested.length).toBeGreaterThan(before);
  });

  test("flags data that has gone stale", async ({ page }) => {
    await page.clock.install();
    await mockDashboard(page);
    await page.goto("/");
    await expect(page.getByText("-$14.88").first()).toBeVisible(); // loaded, so the clock below starts after the first fetch
    await expect(page.getByTestId("stale")).toHaveCount(0);

    await page.unroute(DASHBOARD_API);
    await breakDashboard(page);
    await page.clock.runFor(3 * 60_000); // runFor fires every timer; fastForward fires each only once
    await expect(page.getByTestId("stale")).toBeVisible();
  });
});

test.describe("dashboard without a working API", () => {
  test("shows a clear error with the fix command when nothing ever loaded", async ({ page }) => {
    await breakDashboard(page);
    await page.goto("/");

    const alert = page.getByRole("alert").filter({ hasText: "Couldn't load" });
    await expect(alert).toContainText("Couldn't load the dashboard");
    await expect(alert).toContainText("uv run serve-api");
  });

  test("keeps the last good data and recovers on the next refresh", async ({ page }) => {
    await page.clock.install();
    await mockDashboard(page);
    await page.goto("/");
    await expect(page.getByText("-$14.88").first()).toBeVisible();

    await page.unroute(DASHBOARD_API);
    await breakDashboard(page);
    await page.clock.fastForward(30_000);
    await expect(page.getByRole("alert").filter({ hasText: "Refresh failed" })).toBeVisible();
    await expect(page.getByText("-$14.88").first()).toBeVisible();

    await page.unroute(DASHBOARD_API);
    await mockDashboard(page);
    await page.clock.fastForward(30_000);
    await expect(page.getByText("Refresh failed")).toHaveCount(0);
  });

  test("renders the NO_DATA state without crashing", async ({ page }) => {
    const data = sampleDashboard();
    data.status = { bot_status: "NO_DATA", last_cycle_at: null, last_event: null, message: "no cycle data yet", gate: "ok" };
    data.cycle = null;
    data.recent_trades = [];
    data.open_positions = [];
    await page.route(DASHBOARD_API, (route) => route.fulfill({ json: data }));
    await page.goto("/");

    await expect(page.getByText("NO_DATA")).toBeVisible();
    await expect(page.getByText("No open positions")).toBeVisible();
    await expect(page.getByText("No cycle recorded yet")).toBeVisible();
  });
});
