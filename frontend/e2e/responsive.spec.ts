import { expect, test } from "@playwright/test";

import { crowdedDashboard, mockDashboard } from "./support";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const ZOOMED_IN = { width: 380, height: 900 }; // what a ~500% browser zoom looks like to CSS

test.describe("layout", () => {
  test("desktop: sidebar is visible and cards sit side by side", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await mockDashboard(page);
    await page.goto("/");

    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    await expect(page.getByRole("button", { name: /open menu/i })).toBeHidden();
    const pnl = await page.getByText("Today's P&L", { exact: true }).boundingBox();
    const chart = await page.getByText("Cumulative P&L", { exact: true }).boundingBox();
    expect(pnl && chart && Math.abs(pnl.y - chart.y) < 8).toBe(true);
    expect(chart!.x).toBeGreaterThan(pnl!.x + 200);
  });

  test("desktop: the sidebar highlights the section being viewed", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 700 });
    await mockDashboard(page);
    await page.goto("/");
    await expect(page.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");

    await page.locator("#trades").scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await expect(page.getByRole("link", { name: "Trades" })).toHaveAttribute("aria-current", "page");
  });

  for (const [name, size] of [["phone", PHONE], ["zoomed-in browser", ZOOMED_IN]] as const) {
    test(`${name}: top-bar menu instead of the sidebar, one column, no sideways page scroll`, async ({ page }) => {
      await page.setViewportSize(size);
      await mockDashboard(page, (period) => crowdedDashboard(period));
      await page.goto("/");
      await expect(page.getByTestId("total-pnl")).toBeVisible();

      await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
      await expect(page.getByRole("button", { name: /open menu/i })).toBeVisible();
      const pnl = await page.getByText("Today's P&L", { exact: true }).boundingBox();
      const chart = await page.getByText("Cumulative P&L", { exact: true }).boundingBox();
      expect(chart!.y).toBeGreaterThan(pnl!.y + 100);

      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  test("phone: trades and positions are cards with P&L and R on screen", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await mockDashboard(page, (period) => crowdedDashboard(period));
    await page.goto("/");

    await expect(page.getByRole("table")).toHaveCount(0);
    const trades = page.locator("#trades li").first();
    await expect(trades).toContainText("R");
    const box = await trades.boundingBox();
    expect(box!.x + box!.width).toBeLessThanOrEqual(PHONE.width);
  });

  test("phone: the menu opens, navigates and closes", async ({ page }) => {
    await page.setViewportSize(PHONE);
    await mockDashboard(page);
    await page.goto("/");

    await page.getByRole("button", { name: /open menu/i }).click();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeVisible();
    await page.getByRole("link", { name: "Trades" }).click();
    await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden();
    await expect(page).toHaveURL(/#trades$/);
  });
});

test.describe("theme", () => {
  test("switches to light, and a reload keeps it without a dark flash", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await mockDashboard(page);
    await page.goto("/");
    await expect(page.locator("html")).toHaveClass(/dark/);

    await page.getByRole("button", { name: /switch to light theme/i }).click();
    await expect(page.locator("html")).not.toHaveClass(/dark/);

    await page.reload();
    await expect(page.locator("html")).not.toHaveClass(/dark/);
    await expect(page.getByRole("button", { name: /switch to dark theme/i })).toBeVisible();
  });
});
