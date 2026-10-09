import { describe, expect, it } from "vitest";

import { trade } from "@/test/fixtures";

import { filterTrades, sortTrades, tradesToCsv } from "./trades";

const trades = [
  trade({ symbol: "NVDA", pnl_usd: 1.2, r_multiple: 0.5, closed_at: "2026-10-08T12:32:45-04:00", qty: 10 }),
  trade({ symbol: "BBY", pnl_usd: -7, r_multiple: -0.28, r_source: "proxy", closed_at: "2026-10-08T13:07:50-04:00", qty: 28 }),
  trade({ symbol: "AMD", pnl_usd: 5, r_multiple: null, closed_at: "2026-10-08T11:00:00-04:00", qty: 3 }),
];
const symbols = (list: typeof trades) => list.map((t) => t.symbol);

describe("sortTrades", () => {
  it("sorts text A to Z and Z to A", () => {
    expect(symbols(sortTrades(trades, "symbol", "asc"))).toEqual(["AMD", "BBY", "NVDA"]);
    expect(symbols(sortTrades(trades, "symbol", "desc"))).toEqual(["NVDA", "BBY", "AMD"]);
  });

  it("sorts numbers", () => {
    expect(symbols(sortTrades(trades, "pnl_usd", "desc"))).toEqual(["AMD", "NVDA", "BBY"]);
    expect(symbols(sortTrades(trades, "qty", "asc"))).toEqual(["AMD", "NVDA", "BBY"]);
  });

  it("sorts by close time", () => {
    expect(symbols(sortTrades(trades, "closed_at", "asc"))).toEqual(["AMD", "NVDA", "BBY"]);
  });

  it("keeps trades without an R last, whichever way it sorts", () => {
    expect(symbols(sortTrades(trades, "r_multiple", "asc")).at(-1)).toBe("AMD");
    expect(symbols(sortTrades(trades, "r_multiple", "desc")).at(-1)).toBe("AMD");
  });

  it("does not change the list it is given", () => {
    const before = symbols(trades);
    sortTrades(trades, "symbol", "asc");
    expect(symbols(trades)).toEqual(before);
  });
});

describe("filterTrades", () => {
  it("matches symbols by part, ignoring case and spaces around the text", () => {
    expect(symbols(filterTrades(trades, "  nv "))).toEqual(["NVDA"]);
    expect(symbols(filterTrades(trades, "b"))).toEqual(["BBY"]);
  });

  it("returns everything for an empty query", () => {
    expect(filterTrades(trades, "")).toHaveLength(3);
    expect(filterTrades(trades, "   ")).toHaveLength(3);
  });

  it("returns nothing when nothing matches", () => {
    expect(filterTrades(trades, "zzz")).toEqual([]);
  });
});

describe("tradesToCsv", () => {
  it("starts with a header row and has one row per trade", () => {
    const lines = tradesToCsv(trades).trim().split("\r\n");
    expect(lines[0]).toBe(
      "symbol,qty,entry_price,exit_price,pnl_usd,pnl_pct,r_multiple,r_source,opened_at,closed_at,hold_minutes",
    );
    expect(lines).toHaveLength(4);
  });

  it("writes raw numbers (no currency formatting) and leaves a missing R empty", () => {
    const rows = tradesToCsv(trades).trim().split("\r\n");
    expect(rows[1].startsWith("NVDA,10,235.45,235.57,1.2,0.05,0.5,decision_log,")).toBe(true);
    expect(rows[3].split(",")[6]).toBe("");
  });

  it("marks estimated R values through the r_source column", () => {
    expect(tradesToCsv(trades)).toContain(",proxy,");
  });

  it("quotes values that contain commas or quotes", () => {
    const csv = tradesToCsv([trade({ symbol: 'A,"B"' })]);
    expect(csv).toContain('"A,""B"""');
  });

  it("neutralises spreadsheet formulas in text cells", () => {
    expect(tradesToCsv([trade({ symbol: "=HYPERLINK(1)" })])).toContain("'=HYPERLINK(1)");
  });
});
