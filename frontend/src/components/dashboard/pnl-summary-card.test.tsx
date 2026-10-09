import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { emptyDashboard, sampleDashboard } from "@/test/fixtures";

import { PnlSummaryCard } from "./pnl-summary-card";

describe("PnlSummaryCard", () => {
  it("is titled as today's P&L", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    expect(screen.getByRole("heading", { name: "Today's P&L" })).toBeInTheDocument();
  });

  it("shows the total P&L with its sign", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    const total = screen.getByTestId("total-pnl");
    expect(total).toHaveTextContent("-$14.88");
    expect(total).toHaveAttribute("data-sign", "negative");
  });

  it("marks a profit as positive", () => {
    render(<PnlSummaryCard summary={{ ...sampleDashboard().summary, gross_pnl_usd: 20 }} period="today" />);
    const total = screen.getByTestId("total-pnl");
    expect(total).toHaveTextContent("+$20.00");
    expect(total).toHaveAttribute("data-sign", "positive");
  });

  it("shows wins, losses and win rate", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    expect(within(screen.getByTestId("stat-wins")).getByText("1")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-losses")).getByText("4")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-win-rate")).getByText("20.0%")).toBeInTheDocument();
  });

  it("shows the trade count, profit factor, best and worst trades", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    expect(within(screen.getByTestId("stat-trades")).getByText("5")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-profit-factor")).getByText("0.07")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-best")).getByText("NVDA +$1.20")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-worst")).getByText("BBY -$7.00")).toBeInTheDocument();
  });

  it("shows an infinity sign when there were no losses", () => {
    render(<PnlSummaryCard summary={{ ...sampleDashboard().summary, profit_factor: "inf" }} period="today" />);
    expect(within(screen.getByTestId("stat-profit-factor")).getByText("∞")).toBeInTheDocument();
  });

  it("copes with a day that has no trades", () => {
    render(<PnlSummaryCard summary={emptyDashboard().summary} period="today" />);
    expect(screen.getByTestId("total-pnl")).toHaveTextContent("$0.00");
    expect(screen.getByTestId("total-pnl")).toHaveAttribute("data-sign", "zero");
    expect(within(screen.getByTestId("stat-best")).getByText("—")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-worst")).getByText("—")).toBeInTheDocument();
    expect(within(screen.getByTestId("stat-profit-factor")).getByText("—")).toBeInTheDocument();
  });

  it("mentions which period it summarises", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    expect(screen.getByText("Today · Oct 8")).toBeInTheDocument();
  });

  it("is titled by the selected period", () => {
    const summary = { ...sampleDashboard().summary, from_date: "2026-10-02" };
    render(<PnlSummaryCard summary={summary} period="7d" />);
    expect(screen.getByRole("heading", { name: "P&L" })).toBeInTheDocument();
    expect(screen.getByText("Last 7 days · Oct 2 – Oct 8")).toBeInTheDocument();
  });

  it("marks gains and losses with a symbol as well as a colour", () => {
    render(<PnlSummaryCard summary={sampleDashboard().summary} period="today" />);
    expect(screen.getByTestId("total-pnl").querySelector("[data-marker]")).toHaveTextContent("▼");
  });
});
