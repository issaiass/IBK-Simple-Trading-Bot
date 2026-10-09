import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { position } from "@/test/fixtures";

import { OpenPositionsCard } from "./open-positions-card";

afterEach(() => vi.unstubAllGlobals());

/** Pretend the viewport is a phone, for the card layout. */
function phone() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} })),
  );
}

describe("OpenPositionsCard (table)", () => {
  it("is titled and has the documented columns", () => {
    render(<OpenPositionsCard positions={[position()]} />);
    expect(screen.getByRole("heading", { name: "Open Positions" })).toBeInTheDocument();
    for (const name of ["Symbol", "Qty", "Entry", "Price", "Stop", "Target (+1R)", "Held", "Unrealized R", "P&L"]) {
      expect(screen.getByRole("columnheader", { name })).toBeInTheDocument();
    }
  });

  it("shows a position's values", () => {
    render(<OpenPositionsCard positions={[position()]} />);
    const row = screen.getByRole("row", { name: /BBY/ });
    expect(within(row).getByText("BBY")).toBeInTheDocument();
    expect(within(row).getByText("28")).toBeInTheDocument();
    expect(within(row).getByText("$88.52")).toBeInTheDocument();
    expect(within(row).getByText("$90.90")).toBeInTheDocument();
    expect(within(row).getByText("$83.90")).toBeInTheDocument();
    expect(within(row).getByText("+0.52R")).toBeInTheDocument();
  });

  it("explains the position's state in words", () => {
    render(<OpenPositionsCard positions={[position({ state: "pre_breakeven" })]} />);
    expect(screen.getByText("Waiting for breakeven")).toBeInTheDocument();
  });

  it("shows how far the price is from the stop and from the target", () => {
    render(<OpenPositionsCard positions={[position()]} />);
    expect(screen.getByTestId("stop-distance")).toHaveTextContent("7.70% away");
    expect(screen.getByTestId("target-distance")).toHaveTextContent("2.50% to go");
  });

  it("says when the target has been passed", () => {
    render(<OpenPositionsCard positions={[position({ target_distance_pct: -1.2 })]} />);
    expect(screen.getByTestId("target-distance")).toHaveTextContent("reached");
  });

  it("shows how long the position has been held", () => {
    render(<OpenPositionsCard positions={[position({ hold_minutes: 165 })]} />);
    expect(screen.getByTestId("held")).toHaveTextContent("2h 45m");
    render(<OpenPositionsCard positions={[position({ hold_minutes: null })]} />);
    expect(screen.getAllByTestId("held")[1]).toHaveTextContent("—");
  });

  it("colours unrealized R by its sign", () => {
    render(
      <OpenPositionsCard
        positions={[
          position({ symbol: "UP", unrealized_r: 1.2 }),
          position({ symbol: "DOWN", unrealized_r: -0.4 }),
          position({ symbol: "FLAT", unrealized_r: 0 }),
        ]}
      />,
    );
    const signs = screen.getAllByTestId("unrealized-r").map((el) => el.getAttribute("data-sign"));
    expect(signs).toEqual(["positive", "negative", "zero"]);
  });

  it("shows dashes, not numbers, when there is no live price", () => {
    render(
      <OpenPositionsCard
        positions={[
          position({
            current_price: null, unrealized_r: null, unrealized_pnl_usd: null,
            stop_distance_pct: null, target_distance_pct: null,
          }),
        ]}
      />,
    );
    const cell = screen.getByTestId("unrealized-r");
    expect(cell).toHaveTextContent("—");
    expect(cell).toHaveAttribute("data-sign", "unknown");
    expect(screen.getByTestId("stop-distance")).toHaveTextContent("—");
    expect(screen.getByTestId("target-distance")).toHaveTextContent("—");
  });

  it("shows the unrealized P&L alongside, and a losing one in the loss colour", () => {
    render(<OpenPositionsCard positions={[position(), position({ symbol: "LOSS", unrealized_pnl_usd: -12.5 })]} />);
    expect(screen.getByText("+$66.64")).toBeInTheDocument();
    expect(screen.getByText("-$12.50").closest("td")).toHaveAttribute("data-sign", "negative");
  });

  it("copes with very long symbols and large numbers without breaking the layout classes", () => {
    render(<OpenPositionsCard positions={[position({ symbol: "BRK.B-WARRANT", qty: 123456, entry_price: 12345.67 })]} />);
    expect(screen.getByText("BRK.B-WARRANT")).toBeInTheDocument();
    expect(screen.getByText("$12,345.67")).toBeInTheDocument();
  });

  it("shows how many positions are open", () => {
    render(<OpenPositionsCard positions={[position(), position({ symbol: "PM" })]} />);
    expect(screen.getByTestId("position-count")).toHaveTextContent("2");
  });
});

describe("OpenPositionsCard (empty)", () => {
  it("explains the empty state and what will appear here", () => {
    render(<OpenPositionsCard positions={[]} />);
    expect(screen.getByText("No open positions")).toBeInTheDocument();
    expect(screen.getByText(/appear here/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("OpenPositionsCard (phone)", () => {
  it("lists each position as a card instead of a wide table", () => {
    phone();
    render(<OpenPositionsCard positions={[position(), position({ symbol: "PM" })]} />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("BBY")).toBeInTheDocument();
    expect(within(items[0]).getByText("+0.52R")).toBeInTheDocument();
    expect(within(items[0]).getByText("+$66.64")).toBeInTheDocument();
    expect(within(items[0]).getByText("Waiting for breakeven")).toBeInTheDocument();
  });
});
