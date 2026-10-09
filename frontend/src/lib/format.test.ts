import { describe, expect, it } from "vitest";

import { sampleDashboard } from "@/test/fixtures";

import {
  describeAction,
  formatAge,
  formatClock,
  formatDateTime,
  formatDistance,
  formatGate,
  formatHold,
  formatPct,
  formatPeriodLabel,
  formatPositionState,
  formatPrice,
  formatProfitFactor,
  formatQty,
  formatR,
  formatSignedUsd,
  formatUsd,
  signOf,
} from "./format";

describe("money", () => {
  it("formats dollars with thousands separators and cents", () => {
    expect(formatUsd(1234.5)).toBe("$1,234.50");
    expect(formatUsd(0)).toBe("$0.00");
  });

  it("puts the minus sign before the dollar sign", () => {
    expect(formatUsd(-14.88)).toBe("-$14.88");
  });

  it("shows an explicit sign on signed amounts, but not on zero", () => {
    expect(formatSignedUsd(20)).toBe("+$20.00");
    expect(formatSignedUsd(-7)).toBe("-$7.00");
    expect(formatSignedUsd(0)).toBe("$0.00");
  });

  it("formats prices with two decimals", () => {
    expect(formatPrice(88.5)).toBe("$88.50");
    expect(formatPrice(1070)).toBe("$1,070.00");
  });
});

describe("percent, quantity, profit factor", () => {
  it("formats percentages to the requested digits", () => {
    expect(formatPct(20)).toBe("20.0%");
    expect(formatPct(-0.28, 2)).toBe("-0.28%");
  });

  it("drops a meaningless .0 on whole share counts", () => {
    expect(formatQty(28)).toBe("28");
    expect(formatQty(28.0)).toBe("28");
    expect(formatQty(1.5)).toBe("1.5");
  });

  it("formats numeric, infinite and missing profit factors", () => {
    expect(formatProfitFactor(0.07)).toBe("0.07");
    expect(formatProfitFactor(2.8)).toBe("2.80");
    expect(formatProfitFactor("inf")).toBe("∞");
    expect(formatProfitFactor("n/a")).toBe("—");
  });
});

describe("R-multiples", () => {
  it("shows two decimals and an explicit sign", () => {
    expect(formatR(0.5)).toBe("+0.50R");
    expect(formatR(-0.28)).toBe("-0.28R");
    expect(formatR(0)).toBe("0.00R");
  });

  it("shows a dash when R is not defined", () => {
    expect(formatR(null)).toBe("—");
  });
});

describe("signOf", () => {
  it.each([
    [1.2, "positive"],
    [-0.01, "negative"],
    [0, "zero"],
    [null, "unknown"],
  ] as const)("%s is %s", (value, expected) => {
    expect(signOf(value)).toBe(expected);
  });
});

describe("time (always US Eastern, whatever the browser's zone)", () => {
  it("formats the clock time with an ET suffix", () => {
    expect(formatClock("2026-10-08T12:58:00-04:00")).toBe("12:58 ET");
    expect(formatClock("2026-10-08T16:58:00Z")).toBe("12:58 ET");
  });

  it("formats a short date and time", () => {
    expect(formatDateTime("2026-10-08T12:58:00-04:00")).toBe("Oct 8, 12:58");
  });

  it("accepts a Date too", () => {
    expect(formatClock(new Date("2026-10-08T16:58:00Z"))).toBe("12:58 ET");
  });

  it("formats hold times", () => {
    expect(formatHold(0.6)).toBe("<1m");
    expect(formatHold(1.3)).toBe("1m");
    expect(formatHold(75)).toBe("1h 15m");
    expect(formatHold(120)).toBe("2h");
  });
});

describe("period and market-state wording", () => {
  const summary = (overrides = {}) => ({ ...sampleDashboard().summary, ...overrides });

  it("labels each period for the page", () => {
    expect(formatPeriodLabel("today", summary())).toBe("Today · Oct 8");
    expect(formatPeriodLabel("7d", summary({ from_date: "2026-10-02" }))).toBe("Last 7 days · Oct 2 – Oct 8");
    expect(formatPeriodLabel("30d", summary({ from_date: "2026-09-09" }))).toBe("Last 30 days · Sep 9 – Oct 8");
    expect(formatPeriodLabel("all", summary({ from_date: null }))).toBe("All time");
  });

  it.each([
    ["weekend", "Market closed (weekend)"],
    ["too_early", "Before the 10:00 ET open"],
    ["closed", "Market closed"],
    ["manage_only", "Managing positions only"],
    ["force_close", "Closing positions for the day"],
    ["ok", "Scanning for entries"],
  ] as const)("explains the %s gate in words", (gate, text) => {
    expect(formatGate(gate)).toBe(text);
  });

  it("explains a position's state, and passes unknown states through", () => {
    expect(formatPositionState("pre_breakeven")).toBe("Waiting for breakeven");
    expect(formatPositionState("post_breakeven_no_partial")).toBe("Breakeven, partial pending");
    expect(formatPositionState("post_breakeven_partial_done")).toBe("Partial taken, trailing");
    expect(formatPositionState("something_new")).toBe("something_new");
  });

  it("formats a distance in percent, or a dash", () => {
    expect(formatDistance(4.851)).toBe("4.85%");
    expect(formatDistance(null)).toBe("—");
  });

  it("says how long ago something happened", () => {
    const now = new Date("2026-10-08T17:00:00Z");
    const ago = (s: number) => formatAge(new Date(now.getTime() - s * 1000), now);
    expect(ago(3)).toBe("just now");
    expect(ago(45)).toBe("45s ago");
    expect(ago(200)).toBe("3m ago");
    expect(ago(2 * 3600 + 10)).toBe("2h ago");
  });

  it("describes what the bot did in a cycle", () => {
    expect(describeAction({ event: "entered", symbol: "BBY" })).toBe("Entered BBY");
    expect(describeAction({ event: "partial_sold", symbol: "BBY" })).toBe("Sold a partial of BBY");
    expect(describeAction({ event: "stop_move_failed", symbol: "X" })).toBe("Stop move failed: X");
    expect(describeAction({ event: "max_trades_reached", symbol: null })).toBe("Max trades reached");
  });
});
