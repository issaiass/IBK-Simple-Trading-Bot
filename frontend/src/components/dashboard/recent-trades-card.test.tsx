import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { trade } from "@/test/fixtures";

import { RecentTradesCard } from "./recent-trades-card";

afterEach(() => vi.unstubAllGlobals());

/** jsdom's Blob has no text(), so read it the long way. */
const readBlob = (blob: Blob): Promise<string> =>
  new Promise((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(blob);
  });

const symbolsInOrder = () =>
  screen
    .getAllByRole("row")
    .slice(1)
    .map((row) => within(row).getAllByRole("cell")[0].textContent);

describe("RecentTradesCard", () => {
  it("is titled and has the documented columns", () => {
    render(<RecentTradesCard trades={[trade()]} />);
    expect(screen.getByRole("heading", { name: "Recent Closed Trades" })).toBeInTheDocument();
    for (const name of ["Symbol", "Closed", "Qty", "Entry", "Exit", "P&L", "R"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });

  it("has an accessible caption", () => {
    render(<RecentTradesCard trades={[trade()]} />);
    expect(screen.getByRole("table", { name: /recent closed trades/i })).toBeInTheDocument();
  });

  it("shows a trade's values", () => {
    render(<RecentTradesCard trades={[trade()]} />);
    const row = screen.getByRole("row", { name: /NVDA/ });
    expect(within(row).getByText("NVDA")).toBeInTheDocument();
    expect(within(row).getByText("Oct 8, 12:32")).toBeInTheDocument();
    expect(within(row).getByText("$235.45")).toBeInTheDocument();
    expect(within(row).getByText("$235.57")).toBeInTheDocument();
    expect(within(row).getByText("+$1.20")).toBeInTheDocument();
    expect(within(row).getByText("+0.50R")).toBeInTheDocument();
  });

  it("colour-codes R: green for positive, red for negative", () => {
    render(
      <RecentTradesCard
        trades={[
          trade({ symbol: "UP", r_multiple: 1.5, closed_at: "2026-10-08T15:00:00-04:00" }),
          trade({ symbol: "DOWN", r_multiple: -0.28, closed_at: "2026-10-08T14:00:00-04:00" }),
          trade({ symbol: "FLAT", r_multiple: 0, closed_at: "2026-10-08T13:00:00-04:00" }),
        ]}
      />,
    );
    const signs = screen.getAllByTestId("r-cell").map((el) => el.getAttribute("data-sign"));
    expect(signs).toEqual(["positive", "negative", "zero"]);
  });

  it("colour-codes P&L the same way, with a symbol that does not depend on colour", () => {
    render(
      <RecentTradesCard
        trades={[
          trade({ pnl_usd: -7, closed_at: "2026-10-08T15:00:00-04:00" }),
          trade({ pnl_usd: 3, closed_at: "2026-10-08T14:00:00-04:00" }),
        ]}
      />,
    );
    const cells = screen.getAllByTestId("pnl-cell");
    expect(cells.map((el) => el.getAttribute("data-sign"))).toEqual(["negative", "positive"]);
    expect(cells[0].querySelector("[data-marker]")).toHaveTextContent("▼");
    expect(cells[1].querySelector("[data-marker]")).toHaveTextContent("▲");
  });

  it("flags an estimated R with an est. tag instead of presenting it as measured", () => {
    render(<RecentTradesCard trades={[trade({ r_multiple: -0.28, r_source: "proxy" })]} />);
    const cell = screen.getByTestId("r-cell");
    expect(cell).toHaveTextContent("-0.28R");
    expect(within(cell).getByText("est.")).toBeInTheDocument();
    expect(cell).toHaveAttribute("title", expect.stringMatching(/estimated/i));
    expect(cell).toHaveAttribute("data-estimated", "true");
  });

  it("explains what est. means whenever one is shown", () => {
    render(<RecentTradesCard trades={[trade({ r_source: "proxy" })]} />);
    expect(screen.getByTestId("estimate-legend")).toHaveTextContent(/1% of the entry price/i);
  });

  it("does not flag R that came from a recorded stop, and shows no legend", () => {
    render(<RecentTradesCard trades={[trade({ r_source: "decision_log" })]} />);
    const cell = screen.getByTestId("r-cell");
    expect(cell).toHaveTextContent("+0.50R");
    expect(within(cell).queryByText("est.")).not.toBeInTheDocument();
    expect(cell).toHaveAttribute("data-estimated", "false");
    expect(screen.queryByTestId("estimate-legend")).not.toBeInTheDocument();
  });

  it("shows a dash when R is undefined", () => {
    render(<RecentTradesCard trades={[trade({ r_multiple: null })]} />);
    expect(screen.getByTestId("r-cell")).toHaveTextContent("—");
    expect(screen.getByTestId("r-cell")).toHaveAttribute("data-sign", "unknown");
  });

  it("shows at most the last 20 trades and says so", () => {
    const trades = Array.from({ length: 25 }, (_, i) =>
      trade({ symbol: `S${String(i).padStart(2, "0")}`, closed_at: `2026-10-08T12:${String(59 - i).padStart(2, "0")}:00-04:00` }),
    );
    render(<RecentTradesCard trades={trades} />);
    expect(screen.getAllByTestId("r-cell")).toHaveLength(20);
    expect(screen.getByText("S19")).toBeInTheDocument();
    expect(screen.queryByText("S20")).not.toBeInTheDocument();
    expect(screen.getByTestId("trade-count")).toHaveTextContent("Showing 20 of 25");
  });

  it("explains an empty period", () => {
    render(<RecentTradesCard trades={[]} />);
    expect(screen.getByText("No closed trades in this period")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("copes with long symbols", () => {
    render(<RecentTradesCard trades={[trade({ symbol: "BRK.B-WARRANT-2027" })]} />);
    expect(screen.getByText("BRK.B-WARRANT-2027")).toBeInTheDocument();
  });
});

describe("sorting", () => {
  const trades = [
    trade({ symbol: "BBB", pnl_usd: -7, closed_at: "2026-10-08T14:00:00-04:00" }),
    trade({ symbol: "AAA", pnl_usd: 5, closed_at: "2026-10-08T13:00:00-04:00" }),
    trade({ symbol: "CCC", pnl_usd: 1, closed_at: "2026-10-08T15:00:00-04:00" }),
  ];

  it("starts with the newest trade first", () => {
    render(<RecentTradesCard trades={trades} />);
    expect(symbolsInOrder()).toEqual(["CCC", "BBB", "AAA"]);
    expect(screen.getByRole("columnheader", { name: "Closed" })).toHaveAttribute("aria-sort", "descending");
  });

  it("sorts by a column when its header is clicked, and reverses on a second click", async () => {
    render(<RecentTradesCard trades={trades} />);
    await userEvent.click(screen.getByRole("button", { name: /sort by symbol/i }));
    expect(symbolsInOrder()).toEqual(["AAA", "BBB", "CCC"]);
    expect(screen.getByRole("columnheader", { name: "Symbol" })).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(screen.getByRole("button", { name: /sort by symbol/i }));
    expect(symbolsInOrder()).toEqual(["CCC", "BBB", "AAA"]);
  });

  it("sorts numbers, putting the biggest first on the first click of a money column", async () => {
    render(<RecentTradesCard trades={trades} />);
    await userEvent.click(screen.getByRole("button", { name: /sort by p&l/i }));
    expect(symbolsInOrder()).toEqual(["AAA", "CCC", "BBB"]);
  });

  it("sorts before cutting the list to 20, so the best trades are not hidden", async () => {
    const many = Array.from({ length: 25 }, (_, i) =>
      trade({ symbol: `T${i}`, pnl_usd: i, closed_at: `2026-10-08T12:${String(59 - i).padStart(2, "0")}:00-04:00` }),
    );
    render(<RecentTradesCard trades={many} />);
    await userEvent.click(screen.getByRole("button", { name: /sort by p&l/i }));
    expect(symbolsInOrder()[0]).toBe("T24");
  });
});

describe("filtering", () => {
  const trades = [
    trade({ symbol: "NVDA", closed_at: "2026-10-08T14:00:00-04:00" }),
    trade({ symbol: "BBY", closed_at: "2026-10-08T13:00:00-04:00" }),
  ];

  it("narrows the list as the viewer types a symbol", async () => {
    render(<RecentTradesCard trades={trades} />);
    await userEvent.type(screen.getByRole("searchbox", { name: /filter by symbol/i }), "nv");
    expect(symbolsInOrder()).toEqual(["NVDA"]);
    expect(screen.getByTestId("trade-count")).toHaveTextContent("Showing 1 of 2");
  });

  it("says when nothing matches, and offers a way back", async () => {
    render(<RecentTradesCard trades={trades} />);
    await userEvent.type(screen.getByRole("searchbox", { name: /filter by symbol/i }), "zzz");
    expect(screen.getByText(/no trades match/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /clear filter/i }));
    expect(symbolsInOrder()).toEqual(["NVDA", "BBY"]);
  });
});

describe("export", () => {
  it("downloads the trades as a CSV file", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", { createObjectURL: (b: Blob) => (created.push(b), "blob:x"), revokeObjectURL: () => {} });
    HTMLAnchorElement.prototype.click = vi.fn();
    render(<RecentTradesCard trades={[trade()]} />);
    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));
    expect(created).toHaveLength(1);
    const csv = await readBlob(created[0]);
    expect(csv).toContain("symbol,qty,entry_price");
    expect(csv).toContain("NVDA,10,235.45");
  });

  it("offers no export when there are no trades", () => {
    render(<RecentTradesCard trades={[]} />);
    expect(screen.queryByRole("button", { name: /export csv/i })).not.toBeInTheDocument();
  });

  it("exports what is on screen: the filter applies", async () => {
    const created: Blob[] = [];
    vi.stubGlobal("URL", { createObjectURL: (b: Blob) => (created.push(b), "blob:x"), revokeObjectURL: () => {} });
    HTMLAnchorElement.prototype.click = vi.fn();
    render(<RecentTradesCard trades={[trade({ symbol: "NVDA" }), trade({ symbol: "BBY" })]} />);
    await userEvent.type(screen.getByRole("searchbox", { name: /filter by symbol/i }), "bb");
    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));
    const csv = await readBlob(created[0]);
    expect(csv).toContain("BBY");
    expect(csv).not.toContain("NVDA");
  });
});

describe("phone layout", () => {
  it("lists trades as cards, with P&L and R visible without sideways scrolling", () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} })),
    );
    render(<RecentTradesCard trades={[trade({ symbol: "BBY", pnl_usd: -7, r_multiple: -0.28 })]} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const [item] = screen.getAllByRole("listitem");
    expect(within(item).getByText("BBY")).toBeInTheDocument();
    expect(within(item).getByText("-$7.00")).toBeInTheDocument();
    expect(within(item).getByText("-0.28R")).toBeInTheDocument();
  });
});
