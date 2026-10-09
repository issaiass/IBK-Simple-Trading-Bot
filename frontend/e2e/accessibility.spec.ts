import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { crowdedDashboard, mockDashboard } from "./support";

/** Automated WCAG checks (A and AA). They catch contrast, labels and landmark mistakes, not everything. */
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

for (const theme of ["dark", "light"] as const) {
  test(`has no detectable accessibility violations (${theme} theme)`, async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await mockDashboard(page, (period) => crowdedDashboard(period));
    await page.addInitScript((value) => localStorage.setItem("dashboard.theme", value), theme);
    await page.goto("/");
    await expect(page.getByTestId("total-pnl")).toBeVisible();

    const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    const summary = results.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.length} nodes)`);
    expect(summary).toEqual([]);
  });
}

test("has no detectable accessibility violations on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockDashboard(page, (period) => crowdedDashboard(period));
  await page.goto("/");
  await expect(page.getByTestId("total-pnl")).toBeVisible();

  const results = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(results.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
});

test("the period selector and chart can be used with the keyboard alone", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await mockDashboard(page);
  await page.goto("/");
  await expect(page.getByTestId("total-pnl")).toBeVisible();

  await page.getByRole("radio", { name: "Today" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("radio", { name: "7 days" })).toBeChecked();

  await page.getByRole("group", { name: /chart readout/i }).focus();
  await page.keyboard.press("ArrowLeft");
  await expect(page.getByTestId("readout")).toContainText("NVDA");
});
